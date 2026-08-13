#!/usr/bin/env python3
"""
VPrint Printer Agent — Raspberry Pi (Linux / CUPS)
====================================================
Production-grade agent for Raspberry Pi OS.
Compatible with Raspberry Pi 4 and Raspberry Pi 5.

PRINTING STACK:
  CUPS / lp / lpstat / cancel / lpoptions
  No Windows APIs. No SumatraPDF. No pywin32.

SUPPORTED FILE TYPES:
  - PDF      → pdfinfo + Ghostscript normalization → lp
  - Images   → JPG/PNG/BMP/WEBP/GIF → Pillow → PDF → lp
  - DOCX     → LibreOffice (soffice) → PDF → lp
  - PPTX/PPT → LibreOffice (soffice) → PDF → lp
  - XLSX/XLS → LibreOffice (soffice) → PDF → lp

DUPLEX MAPPING (Brother HL-L2400D / brlaser):
  Portrait  content → Duplex=DuplexNoTumble  (long-edge  flip)
  Landscape content → Duplex=DuplexTumble    (short-edge flip)
  The backend Edge Function (normalize-pdf-orientation) writes the correct
  duplex_mode ('duplex' | 'duplexshort' | 'simplex') into print_jobs.

PAPER / TONER CONSUMPTION:
  - Deducted ONLY after a fully successful physical print.
  - Guarded by paper_deducted / toner_deducted columns (never double-deduct).
  - Single-sided: sheets = pages x copies
  - Double-sided (2+ PDF pages): sheets = ceil(pages/2) x copies — each
    copy is an independent document and does NOT continue onto the
    previous copy's unused back side.
  - Double-sided, EXACTLY 1 PDF page (special case): sheets =
    ceil(copies/2) — copies pair up, two per sheet (front/back).
  - Toner: toner_pages = pages x copies (every side counts)

PAPER / TONER ALERTS:
  - Agent updates paper_alert_state / toner_alert_state in printers table.
  - Supabase triggers + Edge Functions handle Telegram alerts.
  - Agent NEVER sends Telegram directly.

AUTO-PAUSE:
  - When paper_remaining <= auto_pause_threshold: printer paused
  - When toner_remaining <= critical_toner_threshold: printer paused
  - Resume automatically after refill detected.

PAPER RESERVATION:
  - get_available_paper() returns paper_remaining minus reserved sheets.
  - Agent checks available paper before accepting a job.
  - Never allows paper count below zero.

NETWORK RECOVERY:
  - Reconnects Supabase client on connection failure.
  - Resumes polling after WiFi loss.

CRASH RECOVERY:
  - On startup, resets any 'printing' jobs back to 'queued' for this printer.
  - Prevents duplicate printing via paper_deducted / toner_deducted guards.

LOGGING:
  - Rotating daily logs (7-day retention).
  - Separate error log file.
  - Console output.

TELEGRAM:
  - Agent NEVER sends Telegram directly.
  - Inserts rows into telegram_alerts_queue.
  - dispatch_telegram_alerts_worker() POSTs to Supabase Edge Function.

BRANCH_OWNER_TELEGRAM_CHAT_ID:
  - Read from .env for future compatibility.
  - Not used for direct sends.

── NETWORK OPTIMIZATION NOTES (this revision) ──────────────────────────────
  - ETA countdown no longer reads-then-writes Supabase every second.
    It now decrements a local in-memory counter every second and only
    writes to the DB (and recomputes queue positions) every 10 seconds.
    This cuts the countdown thread from ~2 DB calls/sec to ~0.2/sec.
  - TELEGRAM_ALERT_POLL_INTERVAL default raised from 10s to 60s.
    Telegram alerts are already gated by debounce thresholds, so the
    extra dispatch delay is operationally harmless.
  - Job-start printer checks (paper availability + auto-pause) now share
    a single combined `printers` SELECT instead of two separate ones.

── INCIDENT SYSTEM SCOPE (this revision) ────────────────────────────────────
  - Only TWO incident types can trigger printers.incident_status='maintenance':
      paper_jam       — basic, mechanical, needs manual clear
      toner_replace    — new incident type (requires kiosk_incident_type_enum
                          migration: ALTER TYPE ... ADD VALUE 'toner_replace' —
                          already applied on the Supabase side as of this
                          revision).
  - cover_open, offline, paper_empty, and generic printer_error are
    intentionally NOT routed through the incident/maintenance system:
      - cover_open   : rare, physically obvious, handled manually by the
                        on-site printer maintainer.
      - offline      : already surfaced via heartbeat_worker's last_seen
                        staleness — the dashboard can detect a dead Pi/printer
                        without a formal incident.
      - paper_empty  : fully handled by the existing, more specific paper
                        monitoring pipeline (paper_remaining /
                        paper_alert_state / auto_pause_on_no_paper /
                        _update_paper_alert_state), which already sends its
                        own Telegram alerts. Routing it through
                        kiosk_incidents too would be duplicate machinery.
      - printer_error: kept only as a diagnostic log line (logger.warning) —
                        not classified enough to safely auto-trigger
                        maintenance yet.
  - toner_replace incidents ALSO queue a Telegram alert via the existing
    insert_telegram_alert()/send_alert() pipeline (same pattern paper alerts
    already use), in addition to the report_printer_incident() call.

── USB PRESENCE CHECK SCOPE (this revision) ─────────────────────────────────
  - New: is_brother_usb_connected() checks `lsusb` for a Brother-branded
    USB device (vendor ID 04f9, confirmed via the USB-IF vendor database)
    before any file download/processing begins for a job.
  - If the check runs cleanly and finds NO Brother device: the job is
    cancelled/failed and refunded via the SAME job-cancellation pattern
    already used elsewhere in this file (e.g. the insufficient-paper
    guard) — mark the job failed with an error_message and queue a
    Telegram alert. This does NOT call report_printer_incident() and
    does NOT call _set_paused(True) — a disconnected USB cable is not
    routed into the kiosk_incidents/maintenance/test-page flow.
  - If `lsusb` itself fails, errors, times out, or isn't installed: FAIL
    OPEN. The check is skipped, the error is logged, and the job proceeds
    normally — a broken/missing lsusb must never itself block printing.

── SNMP DUPLEX SIDE-COUNTING FIX (this revision) ─────────────────────────────
  - Bug (original): verify_print_via_snmp() was called with
    expected_pages = effective_pages * copies * (2 if double_sided else 1),
    i.e. it doubled the expected physical sides for EVERY duplex job.
    That is wrong for PDFs with 2+ pages: duplex printing doesn't double
    the number of physical sides, it only changes how many sides fit on
    each physical sheet. A 2-page PDF x 4 copies x duplex still only
    produces 8 physical sides (1 sheet per copy, front+back) — not 16.
    The old formula expected 16, so real, correctly-printed duplex jobs
    with 2+ PDF pages would stall-timeout waiting for sides that were
    never coming, and get marked "failed" despite printing perfectly.
  - Fix: expected sides are now computed by the shared helper
    _compute_duplex_expectations(), which distinguishes two cases:
      1. Simplex, OR duplex with 2+ PDF pages:
           expected_sides = pdf_pages * copies
           (each copy is an independent document; it does NOT continue
           onto the previous copy's unused back side)
      2. Duplex with EXACTLY 1 PDF page (special case — copies
         intentionally pair up two-per-sheet, front/back):
           expected_sides = copies * 2
    The same helper also returns expected_sheets (used for the paper
    pre-check), so the two calculations can never drift apart again.
  - The `print_verify_actual_pages` column stays in the same units as
    pages_to_print/total_pages. For the 1-page-duplex special case the
    persisted value is derived by halving the confirmed physical sides
    back down (since 2 sides = 1 "logical" copy-pair unit here); for
    every other case, confirmed sides are used directly since they
    already equal pages * copies.

── STATUS FIELD FIX (this revision) ─────────────────────────────────────────
  - Bug: heartbeat_worker() writes printers.status = current_status every
    HEARTBEAT_INTERVAL seconds, unconditionally. The global current_status
    variable was never set to "offline" when the incident system paused the
    agent, so heartbeat kept overwriting status back to "online" even during
    an active, unresolved incident (confirmed live: printers.status stayed
    "online" through every historical incident, including test_page_pending
    ones). Fixed by having _set_paused() maintain current_status alongside
    the existing INCIDENT_PAUSED flag.

── TELEGRAM QUEUE SCHEMA FIX (this revision) ─────────────────────────────────
  - Bug: insert_telegram_alert() conditionally added a "branch_id" key to the
    telegram_alerts_queue insert payload whenever BRANCH_ID was set in .env.
    telegram_alerts_queue has NO branch_id column (confirmed via live schema
    check: id, printer_id, alert_type, alert_level, value, sent, created_at)
    — every alert insert with BRANCH_ID set was failing with PGRST204.
    Fixed by removing branch_id from the insert payload entirely; printer_id
    already lets any downstream consumer join back to branches via printers.

── SNMP INCIDENT CLASSIFICATION FIX (this revision) ─────────────────────────
  - Bug: when verify_print_via_snmp() detected a fault via alert-text keyword
    match (e.g. "Jam Inside"), the caller in process_job() was reporting a
    hardcoded/fixed incident type rather than the type implied by the actual
    matched keyword — a real paper jam was being misfiled as toner_replace.
    Fixed by having verify_print_via_snmp() return a 3rd value,
    matched_incident_type ("paper_jam" | "toner_replace" | None), classified
    directly from the matched alert text, and having callers use that value
    instead of a hardcoded string. If matched_incident_type is None (fault
    not classifiable as paper_jam or toner_replace), no incident is reported
    — only a warning is logged, consistent with printer_error no longer being
    allowed to auto-trigger maintenance.

── PER-FILE SNMP EXPECTED-PAGE FIX (this revision) ───────────────────────────
  - Bug: for multi-file jobs, verify_print_via_snmp() was called with
    expected_pages computed from `effective_pages` (job.pages_to_print /
    job.total_pages), which is the SUM of pages across every file in the
    job — not the page count of the individual file currently being
    printed. A 2-file job (file 1 = 2 pages, file 2 = 1 page, total = 3)
    would print file 1 correctly (2 physical sides), then SNMP verification
    for file 1 would wait for 3 sides (the job total) instead of 2, stall
    for 30s waiting on a 3rd side that could only come from file 2 (which
    was never sent to CUPS because the loop breaks out on SNMP failure),
    and the job would be wrongly marked failed/refunded despite file 1
    having printed perfectly.
  - Fix: added _get_pdf_page_count() which reads the ACTUAL page count of
    the specific normalized PDF about to be printed via `pdfinfo`. That
    per-file count (not the job-level aggregate) is now passed into
    _compute_duplex_expectations() for the SNMP expected-sides check, so
    each file in a multi-file job is verified against its own page count.

── MULTI-FILE PAPER/ETA OVERCOUNT FIX (this revision) ────────────────────────
  - Bug: `effective_pages` (job.pages_to_print / job.total_pages) is
    already the JOB-LEVEL page total SUMMED across every file (e.g. a
    2-page file + a 1-page file -> effective_pages = 3). Despite a code
    comment explicitly warning "do not multiply it by len(files)",
    needed_sheets, initial_eta, and active_pages_remaining were all doing
    exactly that — multiplying the already-summed total by the file count
    again. For a 2-file job totalling 3 pages this inflated the paper
    pre-check to 6 sheets and the ETA to double the correct value. Real
    impact: multi-file jobs could be wrongly rejected with "insufficient
    paper" even when there was plainly enough, and users saw roughly
    2x-N-x inflated ETAs for an N-file job.
  - Fix: needed_sheets/initial_eta/active_pages_remaining now use
    effective_pages directly (no `* len(files)` multiplier), since it
    already represents the whole job. pages_remaining_after is now tracked
    via a running `cumulative_pages_done` counter updated with each file's
    *actual* page count (from _get_pdf_page_count() / the image case),
    so remaining-ETA reflects real per-file progress instead of a flat
    per-file average of the job total.

── SNMP ALERT KEYWORD NARROWING (this revision) ──────────────────────────────
  - Bug: verify_print_via_snmp()'s _alert_keywords tuple included bare,
    generic words ("error", "fault", "paper", "tray", "cover", "empty").
    Any benign/status text returned by the printer's alert-description OID
    containing one of these substrings (not necessarily an actual fault)
    would abort SNMP verification mid-job and, if unclassifiable, mark a
    perfectly good print job failed/refunded without ever opening an
    incident.
  - Fix: _alert_keywords now only contains the same specific, unambiguous
    fault phrases _classify_snmp_alert_text() already checks for (jam,
    specific toner-low/replace phrases, specific paper/tray-empty phrases,
    specific cover/door-open phrases) instead of single generic words.

── SNMP MULTI-FILE LOGICAL-PAGE FIX (this revision) ──────────────────────────
  - Bug: the job-level SNMP persistence step decided whether to halve the
    total confirmed physical sides (the "duplex + exactly 1 PDF page"
    special case) using `effective_pages == 1` — the JOB-LEVEL total —
    even though the special case is actually decided per file via each
    file's own `file_page_count` during verification. For a multi-file job
    where every individual file is 1 page (so each triggers the special
    case) but the job total is > 1, the job-level check would fail to
    halve, producing a wrong print_verify_actual_pages value.
  - Fix: each file's confirmed physical sides are now converted to
    logical pages immediately (using that file's own file_page_count),
    accumulated into snmp_logical_pages_total, and that running total is
    persisted directly — no second job-level halving decision needed.
"""

import os
import sys
import time
import math
import re
import io
import threading
import tempfile
import subprocess
import logging
import logging.handlers
from pathlib import Path

import requests
from PIL import Image
from dotenv import load_dotenv
from supabase import create_client, Client


# ========================================================================
# LOGGING — Rotating daily logs + error log + console
# ========================================================================

_log_dir = Path("logs")
_log_dir.mkdir(exist_ok=True)

# UTF-8 stdout wrapper
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_LEVEL     = getattr(logging, _LOG_LEVEL_STR, logging.INFO)

_formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")

# Daily rotating main log (keep 7 days)
_rotating_handler = logging.handlers.TimedRotatingFileHandler(
    filename=str(_log_dir / "agent.log"),
    when="midnight",
    backupCount=7,
    encoding="utf-8",
)
_rotating_handler.setFormatter(_formatter)
_rotating_handler.setLevel(_LOG_LEVEL)

# Error-only log (keep 14 days)
_error_handler = logging.handlers.TimedRotatingFileHandler(
    filename=str(_log_dir / "agent_errors.log"),
    when="midnight",
    backupCount=14,
    encoding="utf-8",
)
_error_handler.setFormatter(_formatter)
_error_handler.setLevel(logging.ERROR)

# Console
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_formatter)
_console_handler.setLevel(_LOG_LEVEL)

logging.basicConfig(level=_LOG_LEVEL, handlers=[
    _rotating_handler,
    _error_handler,
    _console_handler,
])
logger = logging.getLogger(__name__)


# ========================================================================
# ENV
# ========================================================================

load_dotenv(override=True)

SUPABASE_URL          = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")
SUPABASE_ANON_KEY     = os.getenv("SUPABASE_ANON_KEY", "")       # future use
PRINTER_ID            = os.getenv("PRINTER_ID")
PRINTER_NAME          = os.getenv("PRINTER_NAME", "")            # CUPS queue name
BRANCH_ID             = os.getenv("BRANCH_ID", "")
BRANCH_OWNER_TELEGRAM_CHAT_ID = os.getenv("BRANCH_OWNER_TELEGRAM_CHAT_ID", "")  # future use

# LibreOffice path (soffice binary on Linux)
LIBREOFFICE_PATH = os.getenv(
    "LIBREOFFICE_PATH",
    "/usr/bin/soffice",   # default apt install path on Raspberry Pi OS
)

# Intervals (seconds)
POLL_INTERVAL                = int(os.getenv("CHECK_INTERVAL",         "15"))
HEARTBEAT_INTERVAL           = int(os.getenv("HEARTBEAT_INTERVAL",     "5"))
PAPER_CHECK_INTERVAL         = 10
SECONDS_PER_PAGE             = 10
TELEGRAM_ALERT_POLL_INTERVAL = int(os.getenv("TELEGRAM_ALERT_POLL_INTERVAL", "10"))  # was 10
DUPLEX_MODE_WAIT_MAX         = 8   # seconds to wait for backend duplex_mode
INCIDENT_POLL_INTERVAL       = 5   # how often (s) to poll for test-page trigger while paused

# How often (in seconds) the ETA countdown actually writes to Supabase.
# The countdown itself still ticks every 1s locally in memory.
ETA_DB_WRITE_INTERVAL_SECS   = 10

# ntfy (optional push notifications)
NTFY_TOPIC  = os.getenv("NTFY_TOPIC",  "")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOKEN  = os.getenv("NTFY_TOKEN",  "")

EDGE_FUNCTION_URL = (
    f"{SUPABASE_URL}/functions/v1/send-telegram-alert"
    if SUPABASE_URL else None
)

# ── Incident edge-function URLs ──────────────────────────────────────────────
# These are the three Edge Functions Claude deployed. We call them via HTTP.
# verify_jwt: false — we authenticate with Bearer + service role key.
REPORT_INCIDENT_URL     = f"{SUPABASE_URL}/functions/v1/report-printer-incident" if SUPABASE_URL else None
CONFIRM_TEST_PAGE_URL   = f"{SUPABASE_URL}/functions/v1/confirm-test-page-result" if SUPABASE_URL else None
TRIGGER_TEST_PAGE_URL   = f"{SUPABASE_URL}/functions/v1/trigger-test-page"       if SUPABASE_URL else None

# ── Internal secret for incident Edge Functions ──────────────────────────────
KIOSK_INCIDENT_INTERNAL_SECRET = os.getenv("KIOSK_INCIDENT_INTERNAL_SECRET", "")

# ── SNMP physical print verification (branch 6 pilot only) ───────────────────
# Gate: SNMP_ENABLED must be explicitly set to "true" in .env.
# All branches 1-5 leave SNMP_ENABLED unset (or "false") — every SNMP code
# path returns a no-op immediately, preserving byte-identical legacy behavior.
SNMP_ENABLED             = os.getenv("SNMP_ENABLED", "false").strip().lower() == "true"
SNMP_HOST                = os.getenv("SNMP_HOST", "")
SNMP_COMMUNITY           = os.getenv("SNMP_COMMUNITY", "public")
SNMP_PAGE_COUNTER_OID    = os.getenv("SNMP_PAGE_COUNTER_OID",  "1.3.6.1.2.1.43.10.2.1.4.1.1")
SNMP_ALERT_DESC_OID      = os.getenv("SNMP_ALERT_DESC_OID",    "1.3.6.1.2.1.43.18.1.1.8.1.1")
SNMP_VERIFY_TIMEOUT_SECS = int(os.getenv("SNMP_VERIFY_TIMEOUT_SECS", "90"))
SNMP_POLL_INTERVAL_SECS  = float(os.getenv("SNMP_POLL_INTERVAL_SECS", "1"))
SNMP_STALL_TIMEOUT_SECS  = int(os.getenv("SNMP_STALL_TIMEOUT_SECS", "30"))

# ── USB presence check (Brother printer) ──────────────────────────────────────
# Vendor ID 04f9 is registered to Brother Industries, Ltd in the USB-IF
# vendor database (confirmed: https://usb-ids.gowdy.us/read/UD/04f9, and
# cross-checked against a live HL-L2440DW descriptor: USB\VID_04F9&PID_0587).
# We intentionally match on VENDOR ID only, not a single hardcoded product
# ID — different branches run different Brother models (HL-L2400D vs
# HL-L2440DW etc.) with different PIDs, but they all share Brother's VID.
BROTHER_USB_VENDOR_ID = "04f9"

# ── Per-error debounce thresholds (number of consecutive poll hits) ──────────
# Only paper_jam and toner_replace are allowed to trigger an incident report /
# maintenance mode. cover_open, offline, printer_error, paper_empty are
# intentionally excluded from this system (see module docstring above).
DEBOUNCE_THRESHOLDS = {
    "paper_jam":      2,   # 2 consecutive poll hits  (~6 s at 3 s interval)
    "toner_replace":  3,   # 3 consecutive poll hits — toner rarely needs to
                            # be as fast-reacting as a jam, avoid over-firing
                            # on a transient "Toner Low" blip.
}

# Validate required ENV
if not all([SUPABASE_URL, SUPABASE_SERVICE_ROLE, PRINTER_ID]):
    logging.critical(
        "FATAL: Missing required ENV variables: "
        "SUPABASE_URL, SUPABASE_SERVICE_ROLE, PRINTER_ID"
    )
    sys.exit(1)

if not EDGE_FUNCTION_URL:
    logger.warning("EDGE_FUNCTION_URL not derived — Telegram alert dispatch disabled")

if not KIOSK_INCIDENT_INTERNAL_SECRET:
    logger.warning(
        "KIOSK_INCIDENT_INTERNAL_SECRET not set — report-printer-incident and "
        "confirm-test-page-result calls will be rejected (401). Incident "
        "detection/reporting will NOT work until this is set in .env."
    )

if BRANCH_OWNER_TELEGRAM_CHAT_ID:
    logger.info(
        f"BRANCH_OWNER_TELEGRAM_CHAT_ID loaded (future use): "
        f"{BRANCH_OWNER_TELEGRAM_CHAT_ID[:6]}..."
    )


# ========================================================================
# SUPABASE CLIENTS
# ========================================================================

def _create_supabase_client() -> Client:
    """Create a Supabase client with retry on failure."""
    while True:
        try:
            client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)
            logger.info("Supabase client created")
            return client
        except Exception as e:
            logger.error(f"Supabase client creation failed: {e} — retrying in 5s")
            time.sleep(5)


supabase           = _create_supabase_client()
supabase_heartbeat = _create_supabase_client()


# ========================================================================
# GLOBAL STATE
# ========================================================================

current_status         = "online"
active_job_id          = None
active_job_lock        = threading.Lock()
active_pages_remaining = 0
_supabase_lock         = threading.Lock()   # guards supabase client

# ── ETA local countdown state ────────────────────────────────────────────
# The countdown thread decrements this every second in memory. It is only
# flushed to Supabase every ETA_DB_WRITE_INTERVAL_SECS seconds, instead of
# doing a DB read + write every single second.
_eta_local_seconds = 0
_eta_local_lock    = threading.Lock()

# ── Phase 3: Incident state ──────────────────────────────────────────────────
# When True the main job loop must NOT accept or process any new normal jobs.
# The only exit from paused state is a successful test-page flow.
INCIDENT_PAUSED       = False
incident_paused_lock  = threading.Lock()

# Per-error-type rolling counters.  Key = incident_type string (same enum
# values used by handle_printer_incident).  Value = dict with:
#   count         — consecutive poll hits in this error condition
#   first_seen_ts — time.time() of first hit in this run (for wall-clock gate)
_debounce_counters: dict = {}


# ========================================================================
# UTILITY HELPERS
# ========================================================================

def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def _safe_int(val):
    if val is None or val == "" or val == "null":
        return None
    try:
        result = int(val)
        return result if result >= 1 else None
    except (ValueError, TypeError):
        return None


def _cleanup(*paths):
    """Remove temp files, silently ignoring errors."""
    for p in paths:
        if p and os.path.exists(str(p)):
            try:
                os.remove(str(p))
                logger.debug(f"Cleaned up: {p}")
            except Exception as ex:
                logger.debug(f"Cleanup failed for {p}: {ex}")


# ========================================================================
# TELEGRAM ALERT — queued via DB, never sent directly from the Pi
# ========================================================================

def insert_telegram_alert(alert_type: str, alert_level: str, value: str) -> None:
    """
    Insert a row into telegram_alerts_queue.
    The Pi NEVER holds a bot token. The actual send is performed by the
    Supabase Edge Function 'send-telegram-alert'.
    BRANCH_OWNER_TELEGRAM_CHAT_ID is available for future enrichment.

    NOTE: telegram_alerts_queue has NO branch_id column (confirmed via live
    schema: id, printer_id, alert_type, alert_level, value, sent, created_at).
    Do NOT add branch_id to this payload — printer_id already lets any
    downstream consumer join back to branches via the printers table.
    """
    try:
        payload = {
            "printer_id":  PRINTER_ID,
            "alert_type":  alert_type,
            "alert_level": alert_level,
            "value":       str(value),
            "sent":        False,
        }
        supabase.table("telegram_alerts_queue").insert(payload).execute()
        logger.info(
            f"Telegram alert queued: type={alert_type} "
            f"level={alert_level} value={value}"
        )
    except Exception as e:
        logger.error(f"Failed to queue Telegram alert ({alert_type}): {e}")


# ========================================================================
# ntfy PUSH NOTIFICATION (direct, optional)
# ========================================================================

def send_ntfy(title: str, message: str, priority: str = "default", tags: list = None):
    if not NTFY_TOPIC:
        return
    try:
        headers = {"Title": title, "Priority": priority}
        if tags:
            headers["Tags"] = ",".join(tags)
        if NTFY_TOKEN:
            headers["Authorization"] = f"Bearer {NTFY_TOKEN}"
        r = requests.post(
            f"{NTFY_SERVER}/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        logger.info(f"ntfy sent [{priority}]: {title}")
    except Exception as e:
        logger.warning(f"ntfy send failed: {e}")


def send_alert(
    alert_type: str,
    alert_level: str,
    value: str,
    ntfy_title: str,
    ntfy_msg: str,
    priority: str = "default",
    tags: list = None,
):
    """Queue Telegram alert + send ntfy (if configured)."""
    insert_telegram_alert(alert_type, alert_level, value)
    send_ntfy(ntfy_title, ntfy_msg, priority=priority, tags=tags or [])


# ========================================================================
# TELEGRAM ALERT DISPATCHER WORKER
# Polls telegram_alerts_queue and POSTs unsent rows to the Edge Function.
# Replaces pg_net (not enabled in this project).
# ========================================================================

def dispatch_telegram_alerts_worker():
    logger.info("Telegram alert dispatcher thread started")
    while True:
        try:
            if not EDGE_FUNCTION_URL:
                time.sleep(TELEGRAM_ALERT_POLL_INTERVAL)
                continue

            res = (
                supabase.table("telegram_alerts_queue")
                .select("*")
                .eq("printer_id", PRINTER_ID)
                .eq("sent", False)
                .order("created_at", desc=False)
                .limit(10)
                .execute()
            )

            for row in (res.data or []):
                alert_id = row["id"]
                try:
                    payload = {
                        "alert_id":    alert_id,
                        "printer_id":  row["printer_id"],
                        "alert_type":  row["alert_type"],
                        "alert_level": row["alert_level"],
                        "value":       row["value"],
                    }
                    resp = requests.post(
                        EDGE_FUNCTION_URL,
                        json=payload,
                        headers={
                            "Content-Type":  "application/json",
                            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE}",
                            "apikey":        SUPABASE_SERVICE_ROLE,
                        },
                        timeout=20,
                    )
                    if resp.status_code == 200 and resp.json().get("success"):
                        logger.info(f"Telegram alert {alert_id} dispatched OK")
                    else:
                        logger.warning(
                            f"Telegram alert {alert_id} dispatch issue "
                            f"HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                        # Mark sent=True to avoid infinite retry on permanent failures
                        supabase.table("telegram_alerts_queue").update(
                            {"sent": True}
                        ).eq("id", alert_id).execute()
                except Exception as dispatch_err:
                    logger.error(f"Failed to dispatch alert {alert_id}: {dispatch_err}")

        except Exception as e:
            logger.error(f"Telegram alert dispatcher error: {e}")

        time.sleep(TELEGRAM_ALERT_POLL_INTERVAL)


# ========================================================================
# GHOSTSCRIPT + LIBREOFFICE CHECK
# ========================================================================

def _gs_available() -> bool:
    try:
        subprocess.run(["gs", "--version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def _libreoffice_available() -> bool:
    paths = [
        LIBREOFFICE_PATH,
        "/usr/bin/soffice",
        "/usr/lib/libreoffice/program/soffice",
        "/opt/libreoffice/program/soffice",
    ]
    for p in paths:
        if p and os.path.isfile(p):
            return True
    # Also try PATH
    try:
        subprocess.run(["soffice", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


GS_AVAILABLE = _gs_available()
LO_AVAILABLE = _libreoffice_available()

logger.info(
    f"Ghostscript  : {'found' if GS_AVAILABLE else 'NOT found — sudo apt install ghostscript'}"
)
logger.info(
    f"LibreOffice  : {'found' if LO_AVAILABLE else 'NOT found — sudo apt install libreoffice'}"
)


def _get_soffice_bin() -> str:
    """Return the path to the soffice binary."""
    paths = [
        LIBREOFFICE_PATH,
        "/usr/bin/soffice",
        "/usr/lib/libreoffice/program/soffice",
        "/opt/libreoffice/program/soffice",
    ]
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return "soffice"  # Fall back to PATH


# ========================================================================
# LIBREOFFICE CONVERSION (DOCX / PPTX / PPT / XLSX / XLS -> PDF)
# ========================================================================

def convert_office_to_pdf(file_path: str) -> str:
    """
    Convert DOCX/PPTX/PPT/XLSX/XLS to PDF using LibreOffice headless.
    Returns path to converted PDF, or original path on failure.
    """
    if not LO_AVAILABLE:
        logger.warning(f"LibreOffice not available — sending '{file_path}' raw")
        return file_path

    soffice = _get_soffice_bin()
    out_dir  = tempfile.gettempdir()
    stem     = Path(file_path).stem
    out_pdf  = os.path.join(out_dir, stem + ".pdf")

    # Remove stale output if exists
    _cleanup(out_pdf)

    cmd = [
        soffice,
        "--headless",
        "--norestore",
        "--nocrashreport",
        "--convert-to", "pdf",
        "--outdir", out_dir,
        file_path,
    ]

    logger.info(f"LibreOffice: converting {Path(file_path).suffix} -> PDF")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.error(
                f"LibreOffice failed (rc={result.returncode}): "
                f"{(result.stderr or result.stdout)[:300]}"
            )
            return file_path

        if os.path.exists(out_pdf) and os.path.getsize(out_pdf) > 100:
            logger.info(f"LibreOffice: converted -> {out_pdf}")
            return out_pdf

        # LibreOffice sometimes puts file in different location — search
        for candidate in Path(out_dir).glob(f"{stem}*.pdf"):
            if candidate.stat().st_size > 100:
                logger.info(f"LibreOffice: found output at {candidate}")
                return str(candidate)

        logger.error("LibreOffice produced no output file")
        return file_path

    except subprocess.TimeoutExpired:
        logger.error("LibreOffice conversion timed out")
        return file_path
    except Exception as e:
        logger.error(f"LibreOffice conversion exception: {e}")
        return file_path


# ========================================================================
# PDF ANALYSIS — orientation + full bleed
# ========================================================================

def _analyze_pdf(path: str) -> tuple:
    """
    Returns (orientation, is_full_bleed).
    'orientation' is 'portrait' or 'landscape'.
    Tries pdfinfo first, then gs bbox as fallback.
    """
    orientation   = "portrait"
    is_full_bleed = False
    w_pts, h_pts  = 0.0, 0.0

    # pdfinfo
    try:
        result = subprocess.run(
            ["pdfinfo", path],
            capture_output=True, text=True, timeout=15,
        )
        for line in result.stdout.splitlines():
            if "Page size" in line:
                parts = line.split()
                if len(parts) >= 5:
                    w_pts = float(parts[2])
                    h_pts = float(parts[4].rstrip(")").strip())
                    if h_pts > 0:
                        ratio       = w_pts / h_pts
                        orientation = "landscape" if ratio > 1.2 else "portrait"
                        is_full_bleed = (w_pts > 600 or h_pts > 850)
                        logger.info(
                            f"pdfinfo: {w_pts:.0f}x{h_pts:.0f}pt "
                            f"ratio={ratio:.3f} -> {orientation}"
                        )
    except FileNotFoundError:
        logger.warning("pdfinfo not found — install: sudo apt install poppler-utils")
    except Exception as e:
        logger.warning(f"pdfinfo failed: {e}")

    # gs bbox fallback
    if GS_AVAILABLE:
        try:
            result = subprocess.run(
                ["gs", "-q", "-dBATCH", "-dNOPAUSE",
                 "-dFirstPage=1", "-dLastPage=1",
                 "-sDEVICE=bbox", path],
                capture_output=True, text=True, timeout=15,
            )
            for line in (result.stdout + result.stderr).splitlines():
                if "%%BoundingBox:" in line:
                    parts = line.split()
                    if len(parts) == 5:
                        x1, y1, x2, y2 = map(int, parts[1:])
                        threshold = 10
                        if x1 < threshold or y1 < threshold:
                            is_full_bleed = True
                        elif w_pts > 0 and h_pts > 0:
                            if (w_pts - x2) < threshold or (h_pts - y2) < threshold:
                                is_full_bleed = True
                        logger.info(
                            f"gs bbox: {x1},{y1}->{x2},{y2} "
                            f"is_full_bleed={is_full_bleed}"
                        )
                        break
        except Exception as e:
            logger.warning(f"gs bbox failed: {e}")

    return orientation, is_full_bleed


def _get_pdf_page_count(path: str) -> "int | None":
    """
    Returns the number of pages in THIS specific PDF via `pdfinfo`, or
    None if it cannot be determined.

    Why this exists: job.pages_to_print / job.total_pages are JOB-LEVEL
    aggregates — for a multi-file job they are the SUM of pages across
    every file (e.g. file 1 = 2 pages + file 2 = 1 page -> total = 3).
    Per-file SNMP verification and per-file ETA must be checked against
    THIS file's own page count, not that job-wide total, or a multi-file
    job will stall waiting for pages that can only come from a later
    file that hasn't been sent to the printer yet (see module docstring,
    "PER-FILE SNMP EXPECTED-PAGE FIX").
    """
    try:
        result = subprocess.run(
            ["pdfinfo", path],
            capture_output=True, text=True, timeout=15,
        )
        for line in result.stdout.splitlines():
            if line.strip().startswith("Pages:"):
                try:
                    return int(line.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    return None
    except Exception as e:
        logger.debug(f"_get_pdf_page_count failed for {path}: {e}")
    return None


# ========================================================================
# PDF -> A4 NORMALIZATION via Ghostscript
# ========================================================================

def _normalize_pdf_simple(path: str) -> str:
    output_path = path + ".a4simple.pdf"
    try:
        cmd = [
            "gs", "-q", "-dBATCH", "-dNOPAUSE", "-dSAFER",
            "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
            "-sPAPERSIZE=a4", "-dFIXEDMEDIA", "-dPDFFitPage",
            "-dAutoRotatePages=/None", "-dRotatePages=false",
            f"-sOutputFile={output_path}", path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.error(f"GS fallback error: {result.stderr.strip()[:200]}")
            return path
        logger.info(f"PDF normalized (simple) -> {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Simple normalization failed: {e}")
        return path


def normalize_pdf_to_a4(path: str, orientation: str = "portrait") -> str:
    """
    Normalize PDF to exact A4 canvas via Ghostscript.
    -dRotatePages=false       -> stop GS rotating pages internally.
    -dAutoRotatePages=/None   -> keep detected orientation intact.
    """
    if not GS_AVAILABLE:
        logger.warning("Ghostscript unavailable — skipping normalization")
        return path

    output_path  = path + ".a4.pdf"
    w_pts, h_pts = (842, 595) if orientation == "landscape" else (595, 842)

    cmd = [
        "gs", "-q", "-dBATCH", "-dNOPAUSE", "-dSAFER",
        "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
        "-dAutoRotatePages=/None",
        "-dRotatePages=false",
        f"-dDEVICEWIDTHPOINTS={w_pts}",
        f"-dDEVICEHEIGHTPOINTS={h_pts}",
        "-dFIXEDMEDIA",
        "-dPDFFitPage",
        f"-sOutputFile={output_path}",
        path,
    ]

    try:
        logger.info(f"Normalizing PDF -> A4 {orientation} ({w_pts}x{h_pts}pt)")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            logger.error(f"GS error (rc={result.returncode}): {result.stderr.strip()[:200]}")
            return _normalize_pdf_simple(path)

        if not os.path.exists(output_path) or os.path.getsize(output_path) < 100:
            logger.error("GS produced empty file — using original")
            return path

        logger.info(f"PDF normalized -> {output_path}")
        return output_path

    except subprocess.TimeoutExpired:
        logger.error("GS normalization timed out — using original")
        return path
    except Exception as e:
        logger.error(f"PDF normalization exception: {e}")
        return path


# ========================================================================
# IMAGE -> PDF CONVERSION
# ========================================================================

def convert_image_to_pdf(path: str) -> str:
    """Convert image to A4 PDF centred on white canvas (180 dpi)."""
    A4_W_PX, A4_H_PX = 1488, 2102   # A4 at 180 dpi
    MARGIN = 100

    try:
        img = Image.open(path)

        if img.mode != "RGB":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode in ("RGBA", "LA", "P"):
                rgba = img.convert("RGBA")
                bg.paste(rgba, mask=rgba.split()[-1])
            else:
                bg.paste(img.convert("RGB"))
            img = bg

        is_landscape = img.width > img.height
        canvas_w     = A4_H_PX if is_landscape else A4_W_PX
        canvas_h     = A4_W_PX if is_landscape else A4_H_PX

        img.thumbnail(
            (canvas_w - 2 * MARGIN, canvas_h - 2 * MARGIN),
            Image.LANCZOS,
        )

        canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
        canvas.paste(img, ((canvas_w - img.width) // 2, (canvas_h - img.height) // 2))

        pdf_path = path + ".pdf"
        canvas.save(pdf_path, "PDF", resolution=180)
        logger.info(
            f"Image->PDF: {img.width}x{img.height}px "
            f"on {canvas_w}x{canvas_h} -> {pdf_path}"
        )
        return pdf_path

    except Exception as e:
        logger.error(f"Image->PDF error: {e}")
        return path


# ========================================================================
# BROTHER DUPLEX OPTION MAPPING
# Brother HL-L2400D / brlaser driver uses Duplex= NOT sides=
# Confirmed via: lpoptions -p "Brother-HL-L2400D" -l
#   Duplex/2-Sided Printing: *None DuplexNoTumble DuplexTumble
# ========================================================================

def _resolve_brother_duplex(
    double_sided: bool,
    duplex_mode_db,
    pdf_orientation: str,
) -> str:
    """
    Returns the correct Brother PPD Duplex= value.
    single-sided     -> None
    portrait duplex  -> DuplexNoTumble  (long-edge  flip = textbook)
    landscape duplex -> DuplexTumble    (short-edge flip = textbook)

    Priority 1: backend-resolved duplex_mode from normalize-pdf-orientation
    Priority 2: local pdf_orientation detection fallback
    """
    if not double_sided:
        logger.info("Duplex: None (single-sided)")
        return "None"

    if duplex_mode_db == "simplex":
        logger.info("Duplex: None (backend said simplex)")
        return "None"

    if duplex_mode_db == "duplex":
        logger.info("Duplex: DuplexNoTumble (backend -> portrait, long-edge)")
        return "DuplexNoTumble"

    if duplex_mode_db == "duplexshort":
        logger.info("Duplex: DuplexTumble (backend -> landscape, short-edge)")
        return "DuplexTumble"

    # Fallback: local detection
    if pdf_orientation == "landscape":
        logger.info("Duplex: DuplexTumble (local detect -> landscape, short-edge)")
        return "DuplexTumble"

    logger.info("Duplex: DuplexNoTumble (local detect -> portrait, long-edge)")
    return "DuplexNoTumble"


# ========================================================================
# PRINT VIA CUPS / lp
# ========================================================================

def print_file(
    file_path,
    copies=1,
    start_page=None,
    end_page=None,
    color_type="bw",
    double_sided=False,
    duplex_mode_db=None,
    paper_size="A4",
    collate=True,
    pdf_orientation="portrait",
    is_full_bleed=False,
):
    """
    Sends a file to the printer.
    - On Windows: Uses SumatraPDF.exe
    - On Linux/Raspberry Pi: Uses CUPS via lp
    """
    copies = max(1, int(copies))
    logger.info(f"Copies      : {copies}")

    if sys.platform == "win32":
        # Windows / SumatraPDF print pipeline
        sumatra = os.getenv("SUMATRAPDF_PATH", "SumatraPDF.exe")
        settings_list = [f"{copies}x", "fit"]
        if start_page is not None and end_page is not None:
            settings_list.append(f"{start_page}-{end_page}")
        if color_type == "bw":
            settings_list.append("monochrome")
        else:
            settings_list.append("color")
        if double_sided:
            settings_list.append("duplex")
        if paper_size:
            settings_list.append(f"paper={paper_size.upper()}")

        settings = ",".join(settings_list)
        cmd = [
            sumatra,
            "-print-to",
            PRINTER_NAME if PRINTER_NAME else "default",
            "-print-settings",
            settings,
            "-silent",
            "-exit-on-print",
            str(file_path)
        ]
        logger.info(f"SumatraPDF command: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, check=True, timeout=120, capture_output=True, text=True
            )
            if result.stdout:
                logger.info(f"SumatraPDF stdout: {result.stdout.strip()}")
            if result.stderr:
                logger.warning(f"SumatraPDF stderr: {result.stderr.strip()}")
            return "win-spool"
        except subprocess.TimeoutExpired:
            logger.error("SumatraPDF PRINT TIMEOUT")
            raise
        except subprocess.CalledProcessError as e:
            logger.error(f"SumatraPDF PRINT FAILED: {e.stderr}")
            raise
    else:
        # Linux / CUPS print pipeline
        cmd = ["lp"]
        if PRINTER_NAME:
            cmd.extend(["-d", PRINTER_NAME])

        cmd.extend(["-n", str(copies)])

        if copies > 1 and collate:
            cmd.extend(["-o", "Collate=True"])

        # Color / BW — Brother HL-L2400D is monochrome
        if color_type == "color":
            logger.info("Color       : COLOR requested but printer is mono — printing BW")
        cmd.extend(["-o", "ColorModel=Gray"])
        logger.info("Color       : Gray (monochrome)")

        # Duplex — Brother PPD
        brother_duplex = _resolve_brother_duplex(double_sided, duplex_mode_db, pdf_orientation)
        cmd.extend(["-o", f"Duplex={brother_duplex}"])
        logger.info(
            f"Duplex      : {brother_duplex} "
            f"(double_sided={double_sided}, duplex_mode_db={duplex_mode_db}, "
            f"pdf_orient={pdf_orientation})"
        )

        # Paper size
        size = (paper_size or "A4").upper()
        if size not in ("A4", "LETTER", "LEGAL", "A3"):
            logger.warning(f"Unknown paper size '{size}' -> defaulting A4")
            size = "A4"
        cmd.extend(["-o", f"media={size}"])
        logger.info(f"Paper       : {size}")
        logger.info(f"PDF orient  : {pdf_orientation} | full_bleed={is_full_bleed}")

        # Scaling
        cmd.extend(["-o", "fit-to-page"])
        logger.info("Scaling     : fit-to-page")

        # Page range
        if start_page is not None and end_page is not None:
            try:
                sp, ep = int(start_page), int(end_page)
                if sp >= 1 and ep >= sp:
                    cmd.extend(["-P", f"{sp}-{ep}"])
                    logger.info(f"Page range  : {sp}-{ep}")
                else:
                    logger.warning(f"Invalid page range {sp}-{ep} -> ALL pages")
            except (ValueError, TypeError) as e:
                logger.warning(f"Page range parse error ({e}) -> ALL pages")
        else:
            logger.info("Page range  : ALL")

        cmd.append(str(file_path))
        logger.info(f"lp command  : {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, check=True, timeout=120, capture_output=True, text=True,
            )

            job_id = None
            if result.stdout:
                match = re.search(r"(\S+-\d+)", result.stdout)
                if match:
                    job_id = match.group(1)
                logger.info(f"lp stdout   : {result.stdout.strip()}")

            if result.stderr:
                logger.warning(f"lp stderr   : {result.stderr.strip()}")

            return job_id

        except subprocess.TimeoutExpired:
            logger.error("PRINT TIMEOUT — possible paper jam or empty tray")
            send_alert(
                alert_type="print_timeout",
                alert_level="critical",
                value="timeout",
                ntfy_title="Print Stuck",
                ntfy_msg="Printing is taking too long. Possible paper empty or jam.",
                priority="high",
            )
            raise

        except subprocess.CalledProcessError as e:
            logger.error(f"PRINT FAILED: {e.stderr}")
            send_alert(
                alert_type="print_failed",
                alert_level="critical",
                value="failed",
                ntfy_title="Print Failed",
                ntfy_msg="Printer failed to print. Check paper or connection.",
                priority="urgent",
            )
            raise


# ========================================================================
# USB PRESENCE CHECK (Brother printer)
# ========================================================================

def is_brother_usb_connected():
    """
    Check whether a Brother-branded USB device is currently enumerated on
    the bus, via `lsusb`. Matches on vendor ID 04f9 (Brother Industries,
    Ltd — confirmed via the USB-IF vendor database), not a single
    hardcoded product ID, since different branches run different Brother
    printer models (each with its own PID) that all share Brother's VID.

    Returns
    -------
    True  — a Brother (04f9:xxxx) USB device was found on the bus.
    False — `lsusb` ran successfully and found NO Brother device — we can
            be confident the printer is unplugged/powered off.
    None  — `lsusb` itself failed, errored, timed out, or isn't installed.
            Caller MUST fail open (treat as "assume connected, don't
            block printing") — a broken lsusb must never itself block a
            job.

    No-op (returns None) on Windows — this check targets the Raspberry
    Pi / CUPS / lsusb setup only.
    """
    if sys.platform == "win32":
        return None

    try:
        result = subprocess.run(
            ["lsusb"], capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.warning(
                f"lsusb exited non-zero (rc={result.returncode}) — "
                "failing open (assuming printer connected)"
            )
            return None

        output = (result.stdout or "").lower()
        found  = f"id {BROTHER_USB_VENDOR_ID}:" in output
        logger.debug(f"is_brother_usb_connected: found={found}")
        return found

    except FileNotFoundError:
        logger.warning("lsusb not found — failing open (assuming printer connected)")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("lsusb timed out — failing open (assuming printer connected)")
        return None
    except Exception as e:
        logger.warning(f"lsusb check error: {e} — failing open (assuming printer connected)")
        return None


# ========================================================================
# SNMP PRINT VERIFICATION (branch 6 pilot only)
# ========================================================================
#
# These functions provide physical print verification via SNMP for the
# Brother HL-L2440DW at branch 6 (Shadan Printer).
#
# Gate: Every function exits immediately (no-op) when SNMP_ENABLED=false,
#       preserving byte-identical behavior for branches 1-5 (USB-only).
#
# How it works:
#   1. Read the printer's page counter OID before the job via SNMP.
#   2. After CUPS reports the job done, poll the counter until it increases
#      by the expected page count or a timeout/stall/error is detected.
#   3. Return (True, pages_confirmed, None) on success,
#      (False, pages_so_far, matched_incident_type) on jam / toner / stall /
#      timeout — matched_incident_type is "paper_jam", "toner_replace", or
#      None if the fault wasn't classifiable as either.
#
#   NOTE: `expected_pages` (as passed in by process_job()) represents
#   PHYSICAL SIDES, not logical pages. The caller computes this via
#   _compute_duplex_expectations() (see below), which distinguishes:
#     - simplex, or duplex with 2+ PDF pages -> pdf_pages * copies
#     - duplex with EXACTLY 1 PDF page (special case, copies pair up
#       two-per-sheet) -> copies * 2
#   See the module docstring ("SNMP DUPLEX SIDE-COUNTING FIX") for the
#   full reasoning.
# ========================================================================

def _compute_duplex_expectations(pdf_pages: int, copies: int, double_sided: bool) -> "tuple[int, int]":
    """
    Returns (expected_sides, expected_sheets) for ONE file.

    Rules:
      - Simplex:
            expected_sides  = pdf_pages * copies
            expected_sheets = pdf_pages * copies

      - Duplex, pdf_pages == 1 (SPECIAL CASE — copies intentionally pair
        up two-per-sheet, front/back of the same sheet):
            expected_sides  = copies * 2
            expected_sheets = ceil(copies / 2)

      - Duplex, pdf_pages >= 2 (each copy is an INDEPENDENT document —
        it does NOT continue onto the previous copy's unused back side):
            expected_sides  = pdf_pages * copies
            expected_sheets = ceil(pdf_pages / 2) * copies

    Examples (all verified against spec):
      1-page  x 4 copies x simplex          -> sides=4,  sheets=4
      1-page  x 2 copies x duplex           -> sides=4,  sheets=1
      1-page  x 4 copies x duplex           -> sides=8,  sheets=2
      1-page  x 17 copies x duplex          -> sides=34, sheets=9
      2-page  x 4 copies x duplex           -> sides=8,  sheets=4
      3-page  x 2 copies x duplex           -> sides=6,  sheets=4
      4-page  x 2 copies x duplex           -> sides=8,  sheets=4
      5-page  x 2 copies x duplex           -> sides=10, sheets=6
      3-page  x 2 copies x simplex          -> sides=6,  sheets=6
    """
    pdf_pages = max(1, int(pdf_pages))
    copies    = max(1, int(copies))

    if double_sided and pdf_pages == 1:
        expected_sides  = copies * 2
        expected_sheets = math.ceil(copies / 2)
    elif double_sided:
        expected_sides  = pdf_pages * copies
        expected_sheets = math.ceil(pdf_pages / 2) * copies
    else:
        expected_sides  = pdf_pages * copies
        expected_sheets = pdf_pages * copies

    return expected_sides, expected_sheets


def snmp_get(oid: str, timeout: int = 5) -> "str | None":
    """
    Run `snmpget -v2c -c <community> -Oqv <host> <oid>` via subprocess.

    Returns the raw string value on success, None on any failure.
    Returns None immediately (no subprocess) when SNMP_ENABLED is false
    or SNMP_HOST is empty — preserving no-op behavior for branches 1-5.
    Never raises.
    """
    if not SNMP_ENABLED or not SNMP_HOST:
        return None
    try:
        result = subprocess.run(
            [
                "snmpget",
                "-v2c",
                "-c", SNMP_COMMUNITY,
                "-Oqv",
                SNMP_HOST,
                oid,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        raw = result.stdout.strip()
        if raw:
            return raw
        return None
    except Exception as e:
        logger.debug(f"snmp_get({oid}) error: {e}")
        return None


def snmp_get_page_counter() -> "int | None":
    """
    Read the printer page-counter OID and return it as an integer.
    Returns None if SNMP is disabled, the OID is unreachable, or the
    value cannot be parsed as an integer.
    """
    raw = snmp_get(SNMP_PAGE_COUNTER_OID)
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        logger.debug(f"snmp_get_page_counter: cannot parse '{raw}' as int")
        return None


def _classify_snmp_alert_text(alert_raw: str) -> "str | None":
    """
    Classify a raw SNMP alert-text string into an incident_type.
    Only paper_jam and toner_replace are recognized as auto-triggerable
    incident types (see module docstring). Anything else — cover, empty,
    generic error/fault, or no match at all — returns None, meaning "log
    it, but do not report an incident."
    """
    if not alert_raw:
        return None
    t = alert_raw.strip().lower()

    if "jam" in t:
        return "paper_jam"

    if any(k in t for k in (
        "toner low", "toner near end", "toner end",
        "replace toner", "no toner",
    )):
        return "toner_replace"

    if any(k in t for k in (
        "paper empty", "media empty", "load tray", "tray empty",
        "out of paper", "no paper", "input tray empty",
    )):
        return "paper_empty"

    return None


def verify_print_via_snmp(
    expected_pages: int,
    progress_log: list,
) -> "tuple[bool, int | None, str | None]":
    """
    Verify that the printer physically produced `expected_pages` pages.

    Parameters
    ----------
    expected_pages : int
        Number of PHYSICAL SIDES expected for this file, as computed by
        the caller via _compute_duplex_expectations().
    progress_log : list
        Mutable list shared across all files in a job; SNMP progress
        entries are appended here for later persistence to Supabase.

    Returns
    -------
    (verified: bool, pages_confirmed: int | None, matched_incident_type: str | None)

    Branch 1-5 behavior (SNMP_ENABLED=false or SNMP_HOST empty):
        Returns (True, None, None) immediately — no subprocess, no side effects.

    Branch 6 behavior (SNMP_ENABLED=true):
        - Reads page counter before polling begins.
        - Polls every SNMP_POLL_INTERVAL_SECS until:
            a. Counter delta >= expected_pages  → (True,  pages_confirmed, None)
            b. Alert OID contains "jam"          → (False, pages_so_far, "paper_jam")
            c. Alert OID contains toner keywords  → (False, pages_so_far, "toner_replace")
            d. Alert OID contains something else
               recognizable as a fault            → (False, pages_so_far, None)
            e. No counter progress for SNMP_STALL_TIMEOUT_SECS
                                                    → (False, pages_so_far, None)
            f. SNMP_VERIFY_TIMEOUT_SECS elapsed    → (False, pages_so_far, None)
        - Fails open: if the initial counter read fails (None), returns
          (True, None, None) so a transient SNMP error never blocks printing.
    """
    # ── Gate: no-op for branches 1-5 ────────────────────────────────────────
    if not SNMP_ENABLED or not SNMP_HOST:
        return (True, None, None)

    # ── Read baseline counter ────────────────────────────────────────────────
    counter_before = snmp_get_page_counter()
    if counter_before is None:
        logger.warning(
            "verify_print_via_snmp: could not read page counter before polling "
            "— failing open to avoid blocking print"
        )
        return (True, None, None)

    logger.info(
        f"SNMP verify: baseline counter={counter_before}, "
        f"expecting {expected_pages} additional page(s)"
    )

    # ── Polling loop ─────────────────────────────────────────────────────────
    pages_confirmed      = 0
    last_counter         = counter_before
    stall_started_at     = time.time()
    overall_started_at   = time.time()

    # NOTE (fixed this revision): this list previously contained bare,
    # generic words ("error", "fault", "paper", "tray", "cover", "empty")
    # which could match benign/status alert-description text and abort
    # verification on a false positive. It now only contains the same
    # specific, unambiguous fault phrases _classify_snmp_alert_text()
    # checks for — jam, specific toner phrases, specific paper/tray-empty
    # phrases, and specific cover/door-open phrases.
    _alert_keywords = (
        "jam",
        "toner low", "toner near end", "toner end", "replace toner", "no toner",
        "paper empty", "media empty", "load tray", "tray empty",
        "out of paper", "no paper", "input tray empty",
        "cover open", "door open",
    )

    while True:
        time.sleep(SNMP_POLL_INTERVAL_SECS)

        now = time.time()

        # ── Overall timeout ──────────────────────────────────────────────────
        if now - overall_started_at >= SNMP_VERIFY_TIMEOUT_SECS:
            logger.warning(
                f"SNMP verify: overall timeout after {SNMP_VERIFY_TIMEOUT_SECS}s "
                f"— confirmed {pages_confirmed}/{expected_pages} pages"
            )
            return (False, pages_confirmed, None)

        # ── Read current counter ─────────────────────────────────────────────
        current_counter = snmp_get_page_counter()
        if current_counter is None:
            logger.debug("SNMP verify: counter read returned None — skipping iteration")
            continue

        delta_total = current_counter - counter_before

        # ── Progress detected ────────────────────────────────────────────────
        if current_counter > last_counter:
            new_pages = current_counter - last_counter
            pages_confirmed = delta_total
            stall_started_at = now   # reset stall timer on any progress
            last_counter = current_counter

            entry = {
                "page":    new_pages,
                "counter": current_counter,
                "t":       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            progress_log.append(entry)
            logger.info(
                f"SNMP verify: +{new_pages} page(s) printed "
                f"(total confirmed={pages_confirmed}/{expected_pages}, "
                f"counter={current_counter})"
            )

        # ── Success: all expected pages confirmed ────────────────────────────
        if pages_confirmed >= expected_pages:
            logger.info(
                f"SNMP verify: SUCCESS — {pages_confirmed}/{expected_pages} "
                f"page(s) confirmed via SNMP"
            )
            return (True, pages_confirmed, None)

        # ── Alert OID check ──────────────────────────────────────────────────
        alert_raw = snmp_get(SNMP_ALERT_DESC_OID)
        logger.debug(f"SNMP poll: alert_raw={alert_raw!r}")
        if alert_raw:
            alert_lower = alert_raw.lower()
            for keyword in _alert_keywords:
                if keyword in alert_lower:
                    matched_type = _classify_snmp_alert_text(alert_raw)
                    logger.warning(
                        f"SNMP verify: alert OID contains '{keyword}' "
                        f"(raw='{alert_raw}') — aborting verification. "
                        f"Confirmed {pages_confirmed}/{expected_pages} pages. "
                        f"Classified as: {matched_type or 'unclassified'}"
                    )
                    return (False, pages_confirmed, matched_type)

        # ── Stall timeout ────────────────────────────────────────────────────
        if now - stall_started_at >= SNMP_STALL_TIMEOUT_SECS:
            logger.warning(
                f"SNMP verify: no page-counter progress for "
                f"{SNMP_STALL_TIMEOUT_SECS}s — stall timeout. "
                f"Confirmed {pages_confirmed}/{expected_pages} pages."
            )
            return (False, pages_confirmed, None)


# ========================================================================
# CUPS JOB COMPLETION TRACKER + ETA COUNTDOWN (merged)
# ========================================================================
#
# job_tracking_worker() replaces two separate mechanisms:
#   • wait_for_job_completion() — polled lpstat every 5 s
#   • eta_countdown_worker()    — always-on daemon thread ticking every 1 s
#
# The merge scopes ETA tracking to an actual active job so the ETA
# countdown never runs when no job is printing. lpstat is polled every
# LPSTAT_POLL_SECS (5 s). The local _eta_local_seconds counter is
# decremented by the same interval on every iteration and flushed to
# Supabase once every ETA_DB_WRITE_INTERVAL_SECS (10 s). On confirmed
# completion the final DB write happens immediately, not at the next
# flush boundary.
# ========================================================================

LPSTAT_POLL_SECS = 5   # how often to call lpstat inside the tracking loop



def job_tracking_worker(supabase_job_id: str, cups_job_id: str) -> bool:
    """
    Tracks a single CUPS job to completion while simultaneously
    maintaining the ETA countdown for that job.

    Called from process_job() after a successful lp submission.
    Returns True immediately on Windows (no CUPS).

    Return values:
      True  — job confirmed done (lpstat no longer lists it), OR
              600 s hard timeout elapsed (assumed done).
      False — subprocess exception while calling lpstat.
    """
    if sys.platform == "win32":
        return True

    global _eta_local_seconds

    logger.info(f"Print mapping:")
    logger.info(f"  Supabase job = {supabase_job_id}")
    logger.info(f"  CUPS job     = {cups_job_id}")
    logger.info(f"Tracking CUPS job: {cups_job_id}")
    start_time      = time.time()
    secs_since_write = 0   # accumulates elapsed time since last DB ETA write

    while True:
        # ── Sleep first (mirrors original wait_for_job_completion behaviour) ──
        time.sleep(LPSTAT_POLL_SECS)

        # ── Decrement local ETA by the poll interval ──────────────────────────
        with _eta_local_lock:
            if _eta_local_seconds > 0:
                _eta_local_seconds = max(0, _eta_local_seconds - LPSTAT_POLL_SECS)
            current_local = _eta_local_seconds

        secs_since_write += LPSTAT_POLL_SECS

        # ── Hard timeout: 600 s — assume done ────────────────────────────────
        if time.time() - start_time > 600:
            logger.warning(f"Tracking timeout for {cups_job_id} — assuming done")
            return True

        # ── Poll lpstat for real completion ───────────────────────────────────
        try:
            res = subprocess.run(
                ["lpstat", "-W", "not-completed"],
                capture_output=True, text=True, timeout=10,
            )
        except Exception as e:
            logger.warning(f"Job tracking error: {e}")
            return False

        if cups_job_id not in res.stdout.strip():
            # ── Job is done: write final ETA (0) immediately, then exit ───────
            logger.info(f"CUPS job {cups_job_id} completed")
            logger.info(f"Supabase job {supabase_job_id} remains the database job ID")
            try:
                supabase.table("print_jobs").update(
                    {"printing_eta_seconds": 0}
                ).eq("id", supabase_job_id).execute()
                update_queue_positions(current_job_eta_seconds=0)
            except Exception:
                pass
            with _eta_local_lock:
                _eta_local_seconds = 0
            return True

        # ── Job still running: flush ETA to Supabase at 10 s cadence ─────────
        if secs_since_write >= ETA_DB_WRITE_INTERVAL_SECS and current_local > 0:
            try:
                supabase.table("print_jobs").update(
                    {"printing_eta_seconds": current_local}
                ).eq("id", supabase_job_id).execute()
                update_queue_positions(current_job_eta_seconds=current_local)
            except Exception:
                pass
            secs_since_write = 0


# ========================================================================
# DOWNLOAD
# ========================================================================

def download_file(url: str, path: str):
    logger.info(f"Downloading -> {path}")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    r = requests.get(url, timeout=60, stream=True)
    r.raise_for_status()

    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)

    size = os.path.getsize(path)
    logger.info(f"Downloaded  : {size:,} bytes -> {path}")

    if size == 0:
        raise RuntimeError(f"Downloaded file is empty: {path}")


# ========================================================================
# SIGNED URL HELPER
# ========================================================================

def _get_signed_url(storage_path: str):
    try:
        res = supabase.storage.from_("print-files").create_signed_url(storage_path, 120)
    except Exception as e:
        logger.error(f"create_signed_url error ({storage_path}): {e}")
        return None

    if isinstance(res, dict):
        return res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
    if isinstance(res, str):
        return res
    if hasattr(res, "data"):
        data = res.data or {}
        return data.get("signedUrl") or data.get("signedURL") or data.get("signed_url")
    return None


# ========================================================================
# PAPER RESERVATION / AVAILABILITY
# ========================================================================

def _get_printer_snapshot(printer_id: str) -> dict:
    """
    Single combined `printers` SELECT covering both paper-availability
    fields and auto-pause fields. Used once at the start of each job so
    get_available_paper_from_data() and _check_auto_pause_from_data()
    don't each need their own round-trip.
    """
    try:
        res = (
            supabase.table("printers")
            .select(
                "paper_remaining, paper_monitoring_enabled, paper_capacity, "
                "auto_pause_on_no_paper, critical_paper_threshold, "
                "toner_remaining, toner_monitoring_enabled, critical_toner_threshold, "
                "auto_pause_on_no_toner, "
                "low_paper_threshold, low_toner_threshold"
            )
            .eq("id", printer_id)
            .single()
            .execute()
        )
        return res.data or {}
    except Exception as e:
        logger.warning(f"_get_printer_snapshot error: {e}")
        return {}


def get_available_paper_from_data(printer_id: str, printer_data: dict) -> int:
    """
    Same logic as get_available_paper(), but takes an already-fetched
    printers row instead of doing its own SELECT. Still queries
    print_jobs separately (different table, still needed for reservations).
    Returns 999999 if monitoring disabled or data missing.
    """
    if not printer_data:
        return 999999

    monitoring = printer_data.get("paper_monitoring_enabled")
    if monitoring is False:
        return 999999

    paper = int(printer_data.get("paper_remaining") or 0)

    # Subtract reserved sheets from active printing jobs
    try:
        active_res = (
            supabase.table("print_jobs")
            .select("total_pages, pages_to_print, copies, double_sided")
            .eq("printer_id", printer_id)
            .in_("status", ["printing", "downloading", "processing"])
            .execute()
        )
        for aj in (active_res.data or []):
            pages  = _safe_int(aj.get("pages_to_print") or aj.get("total_pages")) or 1
            c      = max(1, int(aj.get("copies") or 1))
            ds     = bool(aj.get("double_sided"))
            _, sheets = _compute_duplex_expectations(pages, c, ds)
            paper  = max(0, paper - sheets)
    except Exception as rr:
        logger.warning(f"Reservation check error: {rr}")

    return max(0, paper)


def get_available_paper(printer_id: str) -> int:
    """
    Standalone version (does its own printers SELECT). Kept for any
    caller that doesn't already have a printer snapshot handy.
    Returns effective available paper after subtracting active reservations.
    Never returns negative. Returns large number (999999) if monitoring disabled.
    """
    printer_data = _get_printer_snapshot(printer_id)
    if not printer_data:
        return 999999
    return get_available_paper_from_data(printer_id, printer_data)


# ========================================================================
# PAPER + TONER ALERT STATE UPDATER
# ========================================================================

def _update_paper_alert_state(printer_id: str, paper_remaining: int, printer_data: dict):
    """
    Update paper_alert_state in printers table based on thresholds.
    Supabase triggers handle Telegram + Dashboard updates.

    NOTE (fixed this revision): this function is not currently called
    anywhere in the main loop — paper_alert_state is presently maintained
    by the DB trigger fired from complete_print_job() (see deduct_paper()).
    It is kept here for any future caller. Its field names previously
    referenced "auto_pause" / "auto_pause_threshold", which do not exist
    in the printers snapshot returned by _get_printer_snapshot() (only
    "auto_pause_on_no_paper" / "critical_paper_threshold" do) — that
    mismatch made the auto-pause branch below permanently dead. Fixed to
    use the correct field names so this works correctly if/when wired in.
    """
    try:
        monitoring = printer_data.get("paper_monitoring_enabled")
        if monitoring is False:
            return

        low_threshold      = int(printer_data.get("low_paper_threshold")      or 50)
        critical_threshold = int(printer_data.get("critical_paper_threshold") or 20)
        auto_pause         = bool(printer_data.get("auto_pause_on_no_paper"))
        auto_pause_thresh  = int(printer_data.get("critical_paper_threshold") or 10)

        if paper_remaining <= 0:
            new_state = "out"
        elif paper_remaining <= critical_threshold:
            new_state = "critical"
        elif paper_remaining <= low_threshold:
            new_state = "low"
        else:
            new_state = "ok"

        old_state = printer_data.get("paper_alert_state", "ok") or "ok"

        update_payload = {"paper_alert_state": new_state}

        # Auto-pause: set printer unavailable if paper critically low
        if auto_pause and paper_remaining <= auto_pause_thresh:
            update_payload["status"] = "offline"
            logger.warning(
                f"AUTO-PAUSE: paper_remaining={paper_remaining} "
                f"<= auto_pause_threshold={auto_pause_thresh} -> printer offline"
            )

        supabase.table("printers").update(update_payload).eq("id", printer_id).execute()

        if new_state != old_state:
            logger.info(
                f"Paper alert state: {old_state} -> {new_state} "
                f"(remaining={paper_remaining})"
            )
            if new_state in ("low", "critical", "out"):
                send_alert(
                    alert_type=f"paper_{new_state}",
                    alert_level="critical" if new_state in ("critical", "out") else "warning",
                    value=str(paper_remaining),
                    ntfy_title=f"Paper {new_state.upper()}",
                    ntfy_msg=f"Paper remaining: {paper_remaining} sheets ({new_state})",
                    priority="urgent" if new_state == "out" else "high",
                    tags=["warning", "printer"],
                )

    except Exception as e:
        logger.error(f"Paper alert state update failed: {e}")


def _update_toner_alert_state(printer_id: str, toner_remaining: int, printer_data: dict):
    """
    Update toner_alert_state in printers table based on thresholds.
    Supabase triggers handle Telegram + Dashboard updates.

    NOTE (fixed this revision): same schema-mismatch fix as
    _update_paper_alert_state() above — "auto_pause" is not a field in
    the printers snapshot, "auto_pause_on_no_toner" is.
    """
    try:
        monitoring = printer_data.get("toner_monitoring_enabled")
        if monitoring is False:
            return

        low_threshold      = int(printer_data.get("low_toner_threshold")      or 500)
        critical_threshold = int(printer_data.get("critical_toner_threshold") or 100)

        if toner_remaining <= 0:
            new_state = "out"
        elif toner_remaining <= critical_threshold:
            new_state = "critical"
        elif toner_remaining <= low_threshold:
            new_state = "low"
        else:
            new_state = "ok"

        old_state = printer_data.get("toner_alert_state", "ok") or "ok"

        update_payload = {
            "toner_alert_state": new_state,
            "last_toner_update": _now_utc(),
        }

        # Auto-pause on toner critical/out
        if new_state in ("critical", "out"):
            auto_pause = bool(printer_data.get("auto_pause_on_no_toner"))
            if auto_pause:
                update_payload["status"] = "offline"
                logger.warning(
                    f"AUTO-PAUSE: toner_remaining={toner_remaining} "
                    f"is {new_state} -> printer offline"
                )

        supabase.table("printers").update(update_payload).eq("id", printer_id).execute()

        if new_state != old_state:
            logger.info(
                f"Toner alert state: {old_state} -> {new_state} "
                f"(remaining={toner_remaining})"
            )
            if new_state in ("low", "critical", "out"):
                send_alert(
                    alert_type=f"toner_{new_state}",
                    alert_level="critical" if new_state in ("critical", "out") else "warning",
                    value=str(toner_remaining),
                    ntfy_title=f"Toner {new_state.upper()}",
                    ntfy_msg=f"Toner remaining: {toner_remaining} pages ({new_state})",
                    priority="urgent" if new_state == "out" else "high",
                    tags=["warning", "printer"],
                )

    except Exception as e:
        logger.error(f"Toner alert state update failed: {e}")


# ========================================================================
# PAPER STATUS CHECK (physical CUPS check)
# ========================================================================

def check_paper_status() -> str:
    """
    Returns: 'empty' | 'offline' | 'ok' | 'unknown'
    Uses lpstat — NO database writes.
    """
    try:
        cmd    = (["lpstat", "-p", PRINTER_NAME] if PRINTER_NAME else ["lpstat", "-p"])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = (result.stdout + result.stderr).lower()

        if any(k in output for k in ["media-empty", "out of paper", "paper-empty", "no paper"]):
            return "empty"
        elif any(k in output for k in ["disabled", "offline", "not available", "not connected"]):
            return "offline"
        elif any(k in output for k in ["idle", "ready", "printing", "accepting"]):
            return "ok"
        return "unknown"
    except FileNotFoundError:
        logger.warning("lpstat not found — CUPS may not be installed")
        return "unknown"
    except Exception as e:
        logger.warning(f"Paper check error: {e}")
        return "unknown"


# ========================================================================
# PRINTER HEALTH WORKER (merged paper + USB monitor)
# ========================================================================

def get_available_printers() -> list:
    """Returns list of printer names and logs them (supports Windows and Linux/CUPS)."""
    printers = []
    if sys.platform == "win32":
        try:
            import win32print
            printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
            logger.info(f"Available Windows printers (win32print): {printers}")
            return printers
        except ImportError:
            try:
                result = subprocess.run(
                    ["powershell", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"],
                    capture_output=True, text=True, timeout=10
                )
                printers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
                logger.info(f"Available Windows printers (PowerShell): {printers}")
                return printers
            except Exception as e:
                logger.warning(f"Windows printer detection error: {e}")
                return []
    else:
        try:
            result = subprocess.run(
                ["lpstat", "-a"], capture_output=True, text=True, timeout=10
            )
            if result.stdout:
                logger.info("Available CUPS printers:\n" + result.stdout.strip())
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if parts:
                        printers.append(parts[0])
            else:
                logger.info("No CUPS printers found")
        except FileNotFoundError:
            logger.warning("lpstat not found — CUPS not installed?")
        except Exception as e:
            logger.warning(f"Printer detection error: {e}")
        return printers


def _detect_default_printer():
    """Detect the system default printer (supports Windows and Linux/CUPS)."""
    if sys.platform == "win32":
        try:
            import win32print
            return win32print.GetDefaultPrinter()
        except ImportError:
            try:
                result = subprocess.run(
                    ["powershell", "-Command", "Get-Printer | Where-Object { $_.IsDefault } | Select-Object -ExpandProperty Name"],
                    capture_output=True, text=True, timeout=10
                )
                out = result.stdout.strip()
                if out:
                    return out
            except Exception as e:
                logger.warning(f"Default printer detection error (PowerShell): {e}")
            return None
    else:
        try:
            result = subprocess.run(
                ["lpstat", "-d"], capture_output=True, text=True, timeout=10
            )
            out = result.stdout.strip()
            # "system default destination: Brother-HL-L2400D"
            if "destination:" in out:
                return out.split("destination:")[-1].strip()
        except Exception as e:
            logger.warning(f"Default printer detection error: {e}")
        return None


def printer_health_worker():
    """
    Single daemon thread that combines paper-status monitoring and USB/CUPS
    printer-availability monitoring.

    Loop behaviour:
      1. check_paper_status()    — detects empty / offline / ok transitions
                                   and sends paper_empty / paper_ok alerts.
      2. get_available_printers() — detects removed/added printers, updates
                                   Supabase status, sends printer_offline /
                                   printer_online alerts.
      3. sleep 120 s

    Each check is wrapped in its own try/except so a failure in one does
    not prevent the other from running.
    """
    logger.info("Printer health worker thread started")

    # ── Paper-monitor state ──────────────────────────────────────────────
    last_paper_status = "ok"
    printer_label     = PRINTER_NAME or "VPrint Printer"

    # ── USB-monitor state ────────────────────────────────────────────────
    last_printers = set(get_available_printers())

    time.sleep(20)  # Single startup delay before entering the loop

    while True:
        # ── 1. Paper / CUPS status check ─────────────────────────────────
        try:
            status = check_paper_status()
            now    = time.strftime("%Y-%m-%d %H:%M:%S")

            if status == "empty" and last_paper_status != "empty":
                logger.warning("PAPER EMPTY — sending alert")
                send_alert(
                    alert_type="paper_empty",
                    alert_level="critical",
                    value="empty",
                    ntfy_title=f"Paper Empty — {printer_label}",
                    ntfy_msg=f"Paper tray is empty! Please refill now.\n{now}",
                    priority="urgent",
                    tags=["warning", "printer"],
                )
                last_paper_status = "empty"

            elif status == "ok" and last_paper_status == "empty":
                logger.info("Paper refilled — sending recovery alert")
                send_alert(
                    alert_type="paper_ok",
                    alert_level="info",
                    value="ok",
                    ntfy_title=f"Printer Ready — {printer_label}",
                    ntfy_msg=f"Paper refilled. Printer is ready.\n{now}",
                    priority="default",
                    tags=["white_check_mark", "printer"],
                )
                last_paper_status = "ok"

            elif status == "offline" and last_paper_status != "offline":
                logger.warning("Printer OFFLINE — sending alert")
                send_alert(
                    alert_type="printer_offline",
                    alert_level="critical",
                    value="offline",
                    ntfy_title=f"Printer Offline — {printer_label}",
                    ntfy_msg=f"Printer not responding. Check USB connection.\n{now}",
                    priority="high",
                    tags=["rotating_light", "printer"],
                )
                last_paper_status = "offline"

            elif status == "ok" and last_paper_status == "offline":
                logger.info("Printer back online — sending recovery alert")
                send_alert(
                    alert_type="printer_online",
                    alert_level="info",
                    value="online",
                    ntfy_title=f"Printer Back Online — {printer_label}",
                    ntfy_msg=f"Printer connected and ready.\n{now}",
                    priority="default",
                    tags=["white_check_mark"],
                )
                last_paper_status = "ok"

            if status not in ("empty", "offline"):
                last_paper_status = status

        except Exception as e:
            logger.warning(f"Printer health worker — paper check error: {e}")

        # ── 2. USB / CUPS printer-availability check ──────────────────────
        try:
            current_printers = set(get_available_printers())

            removed = last_printers - current_printers
            added   = current_printers - last_printers

            if removed:
                logger.warning(f"Printer(s) REMOVED: {removed}")
                try:
                    supabase.table("printers").update({
                        "status": "offline",
                    }).eq("id", PRINTER_ID).execute()
                except Exception as db_err:
                    logger.warning(f"DB update on printer remove: {db_err}")

                send_alert(
                    alert_type="printer_offline",
                    alert_level="critical",
                    value=", ".join(removed),
                    ntfy_title=f"Printer Removed — {printer_label}",
                    ntfy_msg=f"Printer disconnected: {', '.join(removed)}",
                    priority="high",
                    tags=["rotating_light"],
                )

            if added:
                logger.info(f"Printer(s) ADDED: {added}")
                try:
                    supabase.table("printers").update({
                        "status": current_status,
                    }).eq("id", PRINTER_ID).execute()
                except Exception as db_err:
                    logger.warning(f"DB update on printer add: {db_err}")

                send_alert(
                    alert_type="printer_online",
                    alert_level="info",
                    value=", ".join(added),
                    ntfy_title=f"Printer Reconnected — {printer_label}",
                    ntfy_msg=f"Printer reconnected: {', '.join(added)}",
                    priority="default",
                    tags=["white_check_mark"],
                )

            last_printers = current_printers

        except Exception as e:
            logger.warning(f"Printer health worker — USB monitor error: {e}")

        # ── 3. Wait before next iteration ─────────────────────────────────
        time.sleep(120)


# ========================================================================
# QUEUE + ETA
# ========================================================================

def update_queue_positions(current_job_eta_seconds: int = 0):
    try:
        queued = (
            supabase.table("print_jobs")
            .select("id, created_at, total_pages, pages_to_print, copies")
            .eq("printer_id",     PRINTER_ID)
            .eq("status",         "queued")
            .eq("payment_status", "paid")
            .order("created_at",  desc=False)
            .execute()
        )
        jobs        = queued.data or []
        accumulated = current_job_eta_seconds

        for pos, job in enumerate(jobs, start=1):
            pages   = (
                _safe_int(job.get("pages_to_print"))
                or _safe_int(job.get("total_pages"))
                or 1
            )
            copies_ = max(1, int(job.get("copies") or 1))
            supabase.table("print_jobs").update({
                "queue_position":    pos,
                "remaining_seconds": accumulated,
            }).eq("id", job["id"]).execute()
            accumulated += pages * copies_ * SECONDS_PER_PAGE

        if jobs:
            logger.info(f"Queue: {len(jobs)} waiting | ETA head: {current_job_eta_seconds}s")
    except Exception as e:
        logger.warning(f"Queue update failed: {e}")


def update_printing_eta(job_id: str, pages_remaining: int):
    """
    Sets the ETA for a job — both in Supabase (so other clients/dashboards
    see it immediately after a file finishes) and in the local countdown
    counter that eta_countdown_worker() decrements every second.
    """
    global active_pages_remaining, _eta_local_seconds
    try:
        eta = max(0, pages_remaining * SECONDS_PER_PAGE)
        active_pages_remaining = pages_remaining

        with _eta_local_lock:
            _eta_local_seconds = eta

        supabase.table("print_jobs").update(
            {"printing_eta_seconds": eta}
        ).eq("id", job_id).execute()
        logger.info(f"ETA -> {eta}s ({pages_remaining} pages remaining)")
        update_queue_positions(current_job_eta_seconds=eta)
    except Exception as e:
        logger.warning(f"ETA update failed: {e}")


# (eta_countdown_worker removed — ETA logic is now inside job_tracking_worker,
#  scoped to an active job. See the CUPS JOB COMPLETION TRACKER section above.)


# ========================================================================
# HEARTBEAT THREAD
# ========================================================================

def heartbeat_worker():
    logger.info("Heartbeat thread started")
    global supabase_heartbeat
    while True:
        try:
            supabase_heartbeat.table("printers").update({
                "status":    current_status,
                "last_seen": _now_utc(),
            }).eq("id", PRINTER_ID).execute()
        except Exception as e:
            logger.warning(f"Heartbeat error: {e}")
            # Reconnect heartbeat client on failure
            try:
                supabase_heartbeat = _create_supabase_client()
            except Exception:
                pass
        time.sleep(HEARTBEAT_INTERVAL)


# ========================================================================
# JOB FINALIZATION GUARD
# ========================================================================

def _job_already_finalized(job_id: str) -> bool:
    """True if the job is already completed — guards against double deduction."""
    try:
        res = (
            supabase.table("print_jobs")
            .select("status, completed_at")
            .eq("id", job_id)
            .execute()
        )
        if res.data:
            row = res.data[0]
            return row.get("status") == "completed" or row.get("completed_at") is not None
    except Exception as e:
        logger.warning(f"Finalized-check failed for job {job_id}: {e}")
    return False


# ========================================================================
# PAPER DEDUCTION
# Runs ONLY after fully successful physical print.
# Idempotent — guarded by paper_deducted column.
# ========================================================================

def deduct_paper(job: dict, copies: int, double_sided: bool) -> None:
    """Consumables deduction is handled atomically by the database trigger on job completion."""
    logger.info(f"Job {job.get('id')}: paper deduction will be handled by the database.")
    return


# ========================================================================
# TONER DEDUCTION
# Every printed side counts as one toner page.
# toner_pages = pages x copies  (same for simplex AND duplex)
# ========================================================================

def deduct_toner(job: dict, copies: int) -> None:
    """Consumables deduction is handled atomically by the database trigger on job completion."""
    logger.info(f"Job {job.get('id')}: toner deduction will be handled by the database.")
    return


# ========================================================================
# AUTO-PAUSE CHECK
# Called before accepting a job. Returns True if printer should pause.
# ========================================================================

def _check_auto_pause_from_data(printer_data: dict) -> bool:
    """
    Same logic as _check_auto_pause(), but takes an already-fetched
    printers row instead of doing its own SELECT.
    Returns True if the printer should NOT accept new jobs due to auto-pause.
    """
    if not printer_data:
        return False

    try:
        # Paper auto-pause
        if printer_data.get("auto_pause_on_no_paper") and printer_data.get("paper_monitoring_enabled"):
            paper     = int(printer_data.get("paper_remaining") or 0)
            threshold = int(printer_data.get("critical_paper_threshold") or 10)
            if paper <= threshold:
                logger.warning(
                    f"AUTO-PAUSE ACTIVE: paper={paper} <= critical_paper_threshold={threshold}"
                )
                return True

        # Toner auto-pause
        if printer_data.get("auto_pause_on_no_toner") and printer_data.get("toner_monitoring_enabled"):
            toner     = int(printer_data.get("toner_remaining") or 0)
            threshold = int(printer_data.get("critical_toner_threshold") or 50)
            if toner <= threshold:
                logger.warning(
                    f"AUTO-PAUSE ACTIVE: toner={toner} <= critical_toner_threshold={threshold}"
                )
                return True

    except Exception as e:
        logger.warning(f"Auto-pause check error: {e}")

    return False


def _check_auto_pause() -> bool:
    """
    Standalone version (does its own printers SELECT). Kept for any
    caller that doesn't already have a printer snapshot handy.
    """
    printer_data = _get_printer_snapshot(PRINTER_ID)
    return _check_auto_pause_from_data(printer_data)


# ========================================================================
# JOB STATUS UPDATER
# ========================================================================

def _update_job_status(job_id: str, status: str, extra: dict = None):
    """Update print_jobs.status with optional extra fields."""
    payload = {"status": status}
    if extra:
        payload.update(extra)
    try:
        supabase.table("print_jobs").update(payload).eq("id", job_id).execute()
        logger.info(f"Job {job_id} status -> {status}")
    except Exception as e:
        logger.warning(f"Job status update failed ({job_id} -> {status}): {e}")


# ========================================================================
# PROCESS JOB
# ========================================================================

def process_job(job: dict):
    global current_status, active_job_id, active_pages_remaining, _eta_local_seconds

    job_id = job.get("id")
    if not job_id:
        logger.error("Job has no ID — skipping")
        return

    # Payment guard — NEVER print unpaid jobs
    if job.get("payment_status") != "paid":
        logger.warning(
            f"Job {job_id}: unpaid "
            f"(payment_status={job.get('payment_status')}) — aborting"
        )
        _update_job_status(job_id, "failed", {
            "error_message": "Unpaid job — payment required"
        })
        return

    # ── Single combined printers snapshot for auto-pause + paper checks ──
    # Replaces two separate SELECTs (_check_auto_pause() + get_available_paper())
    # with one round-trip, reused for both checks below.
    printer_snapshot = _get_printer_snapshot(PRINTER_ID)

    # Auto-pause guard
    if _check_auto_pause_from_data(printer_snapshot):
        logger.warning(f"Job {job_id}: printer is auto-paused — re-queuing")
        _update_job_status(job_id, "queued")
        return

    current_status = "busy"
    with active_job_lock:
        active_job_id = job_id

    logger.info("=" * 60)
    logger.info(f"  Job {job_id}")
    logger.info("=" * 60)

    # -- Job settings -----------------------------------------------
    copies       = max(1, int(job.get("copies") or 1))
    double_sided = bool(job.get("double_sided") or False)
    collate      = bool(
        job.get("collate_pages") if job.get("collate_pages") is not None else True
    )
    paper_size   = job.get("paper_size") or job.get("print_size") or "A4"

    color_type = job.get("color_type") or job.get("print_mode") or "bw"
    if color_type not in ("bw", "color"):
        color_type = "color" if job.get("color") else "bw"

    pages_to_print = _safe_int(job.get("pages_to_print") or job.get("pages"))
    total_pages    = _safe_int(job.get("total_pages"))
    start_page     = _safe_int(job.get("start_page") or job.get("page_from"))
    end_page       = _safe_int(job.get("end_page")   or job.get("page_to"))

    if (
        pages_to_print is not None and total_pages is not None
        and pages_to_print < total_pages
        and start_page is not None and end_page is not None
    ):
        logger.info(f"Page range  : {start_page}-{end_page} ({pages_to_print} of {total_pages})")
    else:
        start_page = None
        end_page   = None
        logger.info(f"Page range  : ALL (pages_to_print={pages_to_print}, total={total_pages})")

    # Backend-resolved duplex_mode from normalize-pdf-orientation Edge Function
    duplex_mode_from_db = (job.get("duplex_mode") or "").strip().lower()
    if duplex_mode_from_db in ("duplex", "duplexshort", "simplex"):
        logger.info(f"Backend duplex_mode : {duplex_mode_from_db}")
    else:
        duplex_mode_from_db = None
        logger.warning("duplex_mode not set by backend — will detect locally from PDF")

    logger.info(f"Copies      : {copies}")
    logger.info(f"Color       : {color_type}")
    logger.info(f"Double-sided: {double_sided}")
    logger.info(f"duplex_mode : {duplex_mode_from_db or 'auto-detect'}")
    logger.info(f"Paper       : {paper_size}")
    logger.info(f"Collate     : {collate}")

    amount = float(job.get("total_price") or job.get("amount") or 0)
    files  = job.get("files") or []
    logger.info(f"Files       : {len(files)}")

    # Check available paper before starting (uses the snapshot fetched above).
    # _compute_duplex_expectations() handles both the "each duplex copy is
    # an independent document" rule (2+ PDF pages) and the special
    # "1-page duplex pairs two copies per sheet" exception in one place, so
    # this stays in lockstep with the SNMP expected-sides calculation below.
    #
    # `effective_pages` is the job-level total across ALL files (e.g. a
    # 2-page file + a 1-page file -> 3). _compute_duplex_expectations()
    # already treats that total as "the whole job's pages", so its sheets
    # output already represents the WHOLE job's paper need — it must NOT
    # be multiplied by len(files) again (that was a real bug: see module
    # docstring "MULTI-FILE PAPER/ETA OVERCOUNT FIX"). A true per-file sheet
    # sum would require each file's own page count up front, which isn't
    # known until each file is downloaded/converted later in the loop —
    # effective_pages remains the best available whole-job estimate.
    effective_pages = pages_to_print or total_pages or 1
    needed_sheets, _ = _compute_duplex_expectations(effective_pages, copies, double_sided)
    available_paper = get_available_paper_from_data(PRINTER_ID, printer_snapshot)

    if available_paper < needed_sheets:
        logger.warning(
            f"Job {job_id}: insufficient paper. "
            f"Need={needed_sheets}, Available={available_paper}"
        )
        send_alert(
            alert_type="paper_insufficient",
            alert_level="critical",
            value=str(available_paper),
            ntfy_title="Insufficient Paper",
            ntfy_msg=(
                f"Job needs {needed_sheets} sheets but only {available_paper} available."
            ),
            priority="urgent",
            tags=["warning"],
        )
        _update_job_status(job_id, "failed", {
            "error_message": (
                f"Insufficient paper: need {needed_sheets}, have {available_paper}"
            )
        })
        with active_job_lock:
            active_job_id = None
        current_status = "online"
        return

    # ── USB presence check (before any file download/processing) ─────────
    # Confirms the Brother printer is actually plugged in before we spend
    # time downloading/converting files for an unreachable printer.
    #   True  -> Brother device found via lsusb, continue normally.
    #   False -> lsusb ran fine, found no Brother device -> cancel this job.
    #   None  -> lsusb itself failed/errored -> FAIL OPEN, continue normally.
    # This intentionally reuses the same job-cancellation pattern as the
    # insufficient-paper guard above (mark failed + send_alert), and does
    # NOT call report_printer_incident()/_set_paused() — a disconnected
    # USB cable does not enter the kiosk_incidents/maintenance/test-page
    # flow.
    usb_present = is_brother_usb_connected()
    if usb_present is False:
        logger.error(
            f"Job {job_id}: Brother printer USB not detected (lsusb) — "
            "cancelling job"
        )
        send_alert(
            alert_type="printer_usb_disconnected",
            alert_level="critical",
            value="disconnected",
            ntfy_title="Printer USB Disconnected",
            ntfy_msg="Printer USB disconnected. Please check the printer USB connection.",
            priority="urgent",
            tags=["warning", "printer"],
        )
        _update_job_status(job_id, "failed", {
            "error_message": "Printer USB disconnected. Please check the printer USB connection."
        })
        with active_job_lock:
            active_job_id = None
        current_status = "online"
        return

    # NOTE (fixed this revision): initial_eta / active_pages_remaining used
    # to multiply effective_pages (already the whole job's page total) by
    # len(files) again, inflating the shown ETA roughly N-fold for an
    # N-file job. effective_pages already represents the whole job, so no
    # len(files) multiplier belongs here — see module docstring "MULTI-FILE
    # PAPER/ETA OVERCOUNT FIX".
    initial_eta            = effective_pages * copies * SECONDS_PER_PAGE
    active_pages_remaining = effective_pages * copies

    # Seed the local ETA countdown so eta_countdown_worker() starts ticking
    # from the correct value immediately, without needing to read it back.
    with _eta_local_lock:
        _eta_local_seconds = initial_eta

    try:
        supabase.table("print_jobs").update(
            {"printing_eta_seconds": initial_eta}
        ).eq("id", job_id).execute()
    except Exception as e:
        logger.warning(f"Could not set initial ETA: {e}")

    update_queue_positions(current_job_eta_seconds=initial_eta)

    all_files_printed      = True
    job_progress_log       = []    # SNMP: accumulated page-counter entries for this job
    snmp_incident_reported = False  # SNMP: only report once per job

    # Running count of ACTUAL pages already sent to the printer, updated
    # with each file's real page count (not a flat per-file average of the
    # job total) — used to compute an accurate pages_remaining_after ETA.
    # See module docstring "MULTI-FILE PAPER/ETA OVERCOUNT FIX".
    cumulative_pages_done = 0

    # Running total of confirmed physical sides converted to LOGICAL pages,
    # accumulated per-file using that file's own page count (rather than a
    # single job-level "effective_pages == 1" decision at the end) — used
    # to persist print_verify_actual_pages correctly for multi-file SNMP
    # jobs. See module docstring "SNMP MULTI-FILE LOGICAL-PAGE FIX".
    snmp_logical_pages_total = 0

    try:
        if not files:
            raise Exception("No files to print")

        for index, file_info in enumerate(files):
            logger.info(f"-- File {index + 1}/{len(files)} --")

            full_path    = file_info.get("url") or ""
            file_name    = str(file_info.get("name") or f"document_{index}.pdf")
            storage_path = (
                full_path.split("print-files/")[-1]
                if "print-files/" in full_path
                else full_path
            )

            if not storage_path:
                logger.error(f"Empty storage path for file {index} — skipping")
                all_files_printed = False
                continue

            # -- Status: downloading ------------------------------------
            _update_job_status(job_id, "downloading")

            file_url = _get_signed_url(storage_path)
            if not file_url:
                logger.error(f"No signed URL for file {index} — skipping")
                all_files_printed = False
                continue

            ext       = Path(file_name).suffix.lower() or ".pdf"
            temp_file = os.path.join(
                tempfile.gettempdir(),
                f"vprint_{job_id}_{index}{ext}"
            )

            try:
                download_file(file_url, temp_file)
            except Exception as e:
                logger.error(f"Download failed for file {index}: {e}")
                all_files_printed = False
                continue

            # -- Status: processing -------------------------------------
            _update_job_status(job_id, "processing")

            original_temp   = temp_file
            pdf_orientation = "portrait"
            is_full_bleed   = False
            converted_file  = None   # track extra converted files for cleanup

            try:
                if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
                    # Image -> PDF
                    try:
                        with Image.open(original_temp) as img_probe:
                            pdf_orientation = (
                                "landscape"
                                if img_probe.width > img_probe.height
                                else "portrait"
                            )
                            logger.info(
                                f"Image {img_probe.width}x{img_probe.height} "
                                f"-> {pdf_orientation}"
                            )
                    except Exception as pe:
                        logger.warning(f"Image probe failed: {pe}")
                    converted_file = convert_image_to_pdf(temp_file)
                    temp_file = converted_file

                elif ext in (".docx", ".doc"):
                    # DOCX -> PDF via LibreOffice
                    logger.info(f"Converting DOCX -> PDF: {file_name}")
                    converted_file = convert_office_to_pdf(original_temp)
                    if converted_file != original_temp:
                        pdf_orientation, is_full_bleed = _analyze_pdf(converted_file)
                        temp_file = normalize_pdf_to_a4(converted_file, pdf_orientation)
                    else:
                        temp_file = converted_file

                elif ext in (".pptx", ".ppt"):
                    # PPTX/PPT -> PDF via LibreOffice
                    logger.info(f"Converting PPTX -> PDF: {file_name}")
                    converted_file = convert_office_to_pdf(original_temp)
                    if converted_file != original_temp:
                        pdf_orientation, is_full_bleed = _analyze_pdf(converted_file)
                        temp_file = normalize_pdf_to_a4(converted_file, pdf_orientation)
                    else:
                        temp_file = converted_file

                elif ext in (".xlsx", ".xls"):
                    # Excel -> PDF via LibreOffice
                    logger.info(f"Converting Excel -> PDF: {file_name}")
                    converted_file = convert_office_to_pdf(original_temp)
                    if converted_file != original_temp:
                        pdf_orientation, is_full_bleed = _analyze_pdf(converted_file)
                        temp_file = normalize_pdf_to_a4(converted_file, pdf_orientation)
                    else:
                        temp_file = converted_file

                elif ext == ".pdf":
                    pdf_orientation, is_full_bleed = _analyze_pdf(temp_file)
                    temp_file = normalize_pdf_to_a4(temp_file, pdf_orientation)

                else:
                    logger.warning(f"Unsupported extension '{ext}' — sending raw to CUPS")

                logger.info(
                    f"PDF orientation FINAL: {pdf_orientation} | "
                    f"full_bleed={is_full_bleed}"
                )

                # ── Determine THIS file's own page count ────────────────
                # (not the job-level total) so per-file SNMP verification
                # and ETA are correct for multi-file jobs. See
                # _get_pdf_page_count() docstring / module docstring
                # "PER-FILE SNMP EXPECTED-PAGE FIX".
                file_page_count = None
                if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
                    file_page_count = 1  # image -> always a single-page PDF
                else:
                    file_page_count = _get_pdf_page_count(str(temp_file))

                if not file_page_count or file_page_count < 1:
                    file_page_count = effective_pages if len(files) == 1 else 1
                    logger.warning(
                        f"Could not determine page count for file {index + 1} "
                        f"— falling back to {file_page_count}"
                    )
                else:
                    logger.info(f"File {index + 1} page count: {file_page_count}")

                # -- Status: printing -----------------------------------
                _update_job_status(job_id, "printing")

                # Remaining ETA now derives from real per-file page counts
                # accumulated so far, instead of a flat
                # `(files_left) * effective_pages` estimate that double
                # counted the job total across files.
                pages_remaining_after = max(
                    0,
                    (effective_pages - cumulative_pages_done - file_page_count) * copies
                )

                try:
                    cups_job_id = print_file(
                        file_path       = str(temp_file),
                        copies          = copies,
                        start_page      = start_page,
                        end_page        = end_page,
                        color_type      = color_type,
                        double_sided    = double_sided,
                        duplex_mode_db  = duplex_mode_from_db,
                        paper_size      = paper_size,
                        collate         = collate,
                        pdf_orientation = pdf_orientation,
                        is_full_bleed   = is_full_bleed,
                    )

                    if cups_job_id:
                        job_tracking_worker(job_id, cups_job_id)
                    else:
                        logger.warning("No CUPS job ID returned — fallback wait")
                        time.sleep(SECONDS_PER_PAGE * copies * 2)

                    logger.info(f"File {index + 1}/{len(files)} sent to printer")
                    cumulative_pages_done += file_page_count
                    update_printing_eta(job_id, pages_remaining_after)

                    # ── SNMP physical verification (branch 6 pilot only) ──────
                    # No-op when SNMP_ENABLED=false (branches 1-5 unaffected).
                    #
                    # expected_file_pages is PHYSICAL SIDES, computed by the
                    # shared _compute_duplex_expectations() helper using
                    # file_page_count (THIS file's own page count — fixed
                    # above) so this always matches the paper pre-check and,
                    # crucially, no longer waits for pages that belong to a
                    # DIFFERENT file in a multi-file job:
                    #   - simplex, or duplex with 2+ PDF pages -> pages*copies
                    #   - duplex with EXACTLY 1 PDF page (special case,
                    #     copies pair up two-per-sheet)         -> copies*2
                    if not snmp_incident_reported:
                        expected_file_pages, _ = _compute_duplex_expectations(
                            file_page_count, copies, double_sided
                        )
                        file_verified, actual_pages, matched_incident_type = verify_print_via_snmp(
                            expected_file_pages, job_progress_log
                        )

                        # Convert THIS file's confirmed physical sides to
                        # logical pages using its OWN page count (not a
                        # job-level decision) and accumulate. See module
                        # docstring "SNMP MULTI-FILE LOGICAL-PAGE FIX".
                        if actual_pages:
                            if double_sided and file_page_count == 1:
                                snmp_logical_pages_total += math.ceil(actual_pages / 2)
                            else:
                                snmp_logical_pages_total += actual_pages

                        if file_verified:
                            if SNMP_ENABLED and SNMP_HOST:
                                logger.info(
                                    f"SNMP: file {index + 1} physically confirmed "
                                    f"({actual_pages}/{expected_file_pages} sides)"
                                )
                        else:
                            # Physical print failure detected via SNMP
                            logger.warning(
                                f"SNMP: file {index + 1} verification FAILED — "
                                f"{actual_pages}/{expected_file_pages} sides confirmed "
                                f"(classified as: {matched_incident_type or 'unclassified'})"
                            )
                            all_files_printed = False
                            # Persist error_message to the job row immediately
                            try:
                                supabase.table("print_jobs").update({
                                    "error_message": (
                                        f"SNMP verification failed: "
                                        f"{actual_pages}/{expected_file_pages} "
                                        f"sides confirmed"
                                    ),
                                }).eq("id", job_id).execute()
                            except Exception as _snmp_db_err:
                                logger.warning(
                                    f"Could not update error_message for SNMP "
                                    f"failure: {_snmp_db_err}"
                                )
                            # Route through existing incident pipeline — ONLY if
                            # the fault was classified as paper_jam or
                            # toner_replace. Anything else is logged but does
                            # NOT auto-trigger an incident/maintenance mode.
                            if matched_incident_type in ("paper_jam", "toner_replace"):
                                _incident_ok = report_printer_incident(
                                    matched_incident_type,
                                    triggered_by_job_id=job_id,
                                )
                                if _incident_ok:        
                                    _set_paused(True)
                                    if matched_incident_type == "toner_replace":
                                        send_alert(
                                            alert_type="toner_replace",
                                            alert_level="critical",
                                            value="toner_replace",
                                            ntfy_title="Toner Replacement Needed",
                                            ntfy_msg=(
                                                "Printer toner needs replacement. "
                                                "Printer paused until resolved."
                                            ),
                                            priority="urgent",
                                            tags=["warning", "printer"],
                                        )
                            elif matched_incident_type == "paper_empty":
                                # Alert-only — no incident/maintenance, no auto-pause. The paper
                                # tray is not a mechanical fault; the existing paper-monitoring
                                # pipeline (check_paper_status / printer_health_worker) will also
                                # pick this up on its own cadence, but this gets the alert out
                                # immediately instead of waiting up to 120s.
                                logger.warning(
                                    f"SNMP: paper_empty detected during print — job {job_id} "
                                    "cancelled and refunded, no incident/maintenance triggered."
                                )
                                send_alert(
                                    alert_type="paper_empty",
                                    alert_level="critical",
                                    value=f"{actual_pages}/{expected_file_pages}",
                                    ntfy_title="Paper Empty",
                                    ntfy_msg=(
                                        f"Printer ran out of paper mid-job "
                                        f"({actual_pages}/{expected_file_pages} sides confirmed). "
                                        "Job was cancelled and refunded. Please refill the tray."
                                    ),
                                    priority="urgent",
                                    tags=["warning", "printer"],
                                )
                            else:
                                logger.warning(
                                    "SNMP: verification failure not classifiable as "
                                    "paper_jam, toner_replace, or paper_empty — sending generic "
                                    "alert; job marked failed only."
                                )
                                send_alert(
                                    alert_type="print_verification_failed",
                                    alert_level="critical",
                                    value=f"{actual_pages}/{expected_file_pages}",
                                    ntfy_title="Print Failed — Unclassified",
                                    ntfy_msg=(
                                        f"Print verification failed ({actual_pages}/{expected_file_pages} "
                                        "sides confirmed). Job was cancelled and refunded."
                                    ),
                                    priority="urgent",
                                    tags=["warning", "printer"],
                                )

                            snmp_incident_reported = True
                            break  # No point printing further files on a paused printer

                except subprocess.CalledProcessError as e:
                    logger.error(
                        f"lp failed for file {index}: "
                        f"rc={e.returncode} | {(e.stderr or '').strip()[:200]}"
                    )
                    all_files_printed = False
                    update_printing_eta(job_id, pages_remaining_after)

                except Exception as e:
                    logger.error(f"Print error for file {index}: {e}")
                    all_files_printed = False
                    update_printing_eta(job_id, pages_remaining_after)

            finally:
                # Clean up all intermediate files
                files_to_clean = set()
                if temp_file != original_temp:
                    files_to_clean.add(temp_file)
                if (
                    converted_file
                    and converted_file != original_temp
                    and converted_file != temp_file
                ):
                    files_to_clean.add(converted_file)
                files_to_clean.add(original_temp)
                _cleanup(*files_to_clean)

        # Zero out ETA
        try:
            supabase.table("print_jobs").update(
                {"printing_eta_seconds": 0}
            ).eq("id", job_id).execute()
        except Exception:
            pass
        with _eta_local_lock:
            _eta_local_seconds = 0

        # ── SNMP: persist verification result (branch 6 only) ────────────────
        # Only writes when SNMP was actually active this job (i.e. SNMP_ENABLED
        # is true and SNMP_HOST is set). Skipped entirely for branches 1-5.
        #
        # snmp_logical_pages_total was accumulated PER FILE during the loop
        # above (each file's confirmed physical sides converted using that
        # file's own page count), so it is correct for both single-file and
        # multi-file jobs — no second job-level halving decision needed here.
        # See module docstring "SNMP MULTI-FILE LOGICAL-PAGE FIX".
        if SNMP_ENABLED and SNMP_HOST:
            _snmp_total_confirmed_sides = sum(e.get("page", 0) for e in job_progress_log)
            try:
                supabase.table("print_jobs").update({
                    "print_progress_log":        job_progress_log,
                    "print_verified":            bool(all_files_printed),
                    "print_verify_actual_pages": snmp_logical_pages_total,
                }).eq("id", job_id).execute()
                logger.info(
                    f"SNMP: persisted verification result — verified={all_files_printed}, "
                    f"logical_pages_confirmed={snmp_logical_pages_total} "
                    f"(physical_sides={_snmp_total_confirmed_sides}), "
                    f"log_entries={len(job_progress_log)}"
                )
            except Exception as _snmp_persist_err:
                logger.warning(f"SNMP: could not persist verification result: {_snmp_persist_err}")

        # -- Consumables deduction (ONLY after all files printed) -----
        if all_files_printed:
            logger.info(
                f"All files printed -> deducting consumables for job {job_id}"
            )
            deduct_paper(job, copies, double_sided)
            deduct_toner(job, copies)

            logger.info(f"Consumables deducted -> completing job {job_id}")
            try:
                result = supabase.rpc("complete_print_job", {
                    "p_job_id":     job_id,
                    "p_user_id":    job.get("user_id"),
                    "p_pages":      int(pages_to_print or total_pages or 1),
                    "p_amount":     amount,
                    "p_printer_id": job.get("printer_id"),
                    "p_branch_id":  job.get("branch_id") or BRANCH_ID or None,
                    "p_file_name": (
                        job.get("file_name")
                        or (files[0].get("name") if files else "document")
                    ),
                }).execute()
                logger.info(f"RPC complete_print_job result: {result.data}")
            except Exception as e:
                logger.error(f"complete_print_job RPC failed: {e}")
                # Fallback: mark completed directly
                try:
                    supabase.table("print_jobs").update({
                        "status":       "completed",
                        "completed_at": _now_utc(),
                    }).eq("id", job_id).execute()
                    logger.info(f"Fallback: job {job_id} marked completed directly")
                except Exception as e2:
                    logger.error(f"Fallback completion failed: {e2}")
        elif snmp_incident_reported:
            # SNMP-detected physical failure — no consumable deduction.
            # Refund is handled by the report-printer-incident Edge Function
            # (only when the fault was classified as paper_jam/toner_replace).
            logger.warning(
                f"SNMP incident reported for job {job_id} — "
                "marking cancelled_incident (no consumable deduction)"
            )
            try:
                supabase.table("print_jobs").update({
                    "status":       "cancelled_incident",
                    "completed_at": _now_utc(),
                }).eq("id", job_id).execute()
            except Exception as e:
                logger.error(f"Could not mark job cancelled_incident: {e}")
        else:
            logger.warning(f"Some files failed -> marking job {job_id} failed")
            try:
                supabase.table("print_jobs").update({
                    "status":        "failed",
                    "error_message": "One or more files failed to print",
                    "completed_at":  _now_utc(),
                }).eq("id", job_id).execute()
            except Exception as e:
                logger.error(f"Could not mark job failed: {e}")

    except Exception as e:
        logger.error(f"Job {job_id} unhandled exception: {e}", exc_info=True)
        try:
            supabase.table("print_jobs").update({
                "status":        "failed",
                "error_message": str(e)[:500],
            }).eq("id", job_id).execute()
        except Exception:
            pass

    finally:
        with active_job_lock:
            active_job_id = None
        active_pages_remaining = 0
        with _eta_local_lock:
            _eta_local_seconds = 0
        # Only reset current_status to "online" if we are not mid-incident —
        # _set_paused(True) may have already set it to "offline", and a
        # completed/failed job finishing in the same cycle must not stomp
        # that back to "online" while INCIDENT_PAUSED is still True.
        if not _is_paused():
            current_status = "online"
        update_queue_positions(current_job_eta_seconds=0)
        logger.info(f"=== Job {job_id} done -> {current_status} ===\n")


# ========================================================================
# CRASH / REBOOT RECOVERY
# On startup, reset any jobs stuck in 'printing' / 'downloading' / 'processing'
# back to 'queued' so they are retried without duplication.
# Paper/toner deduction guards prevent double-deduction even if a job
# partially completed before the crash.
# ========================================================================

def recover_stuck_jobs():
    """
    Reset any jobs stuck in intermediate states back to 'queued'.
    Called once at startup.
    """
    try:
        stuck = (
            supabase.table("print_jobs")
            .select("id, status")
            .eq("printer_id", PRINTER_ID)
            .in_("status", ["printing", "downloading", "processing"])
            .execute()
        )

        if not stuck.data:
            logger.info("Crash recovery: no stuck jobs found")
            return

        for job in stuck.data:
            jid = job["id"]
            # Skip test-page jobs — they are already handled by incident recovery
            logger.warning(
                f"Crash recovery: resetting job {jid} "
                f"(was '{job['status']}') -> queued"
            )
            try:
                supabase.table("print_jobs").update({
                    "status":        "queued",
                    "error_message": f"Recovered from crash (was: {job['status']})",
                    "started_at":    None,
                }).eq("id", jid).execute()
            except Exception as reset_err:
                logger.error(f"Failed to reset stuck job {jid}: {reset_err}")

        logger.info(f"Crash recovery: reset {len(stuck.data)} stuck job(s)")

    except Exception as e:
        logger.error(f"Crash recovery failed: {e}")


# ========================================================================
# PHASE 3 — INCIDENT SYSTEM
# ========================================================================

def _get_cups_error_reasons() -> set:
    """
    Returns the set of active CUPS reason codes for our printer, restricted
    to ONLY the two incident types allowed to auto-trigger maintenance:
    paper_jam and toner_replace (see module docstring).

    Uses `lpstat -p <printer> -l` (long form) which lists 'Reason:' lines.
    Falls back to empty set on any error — never blocks the caller.

    cover_open, offline, paper_empty, and generic printer_error are
    intentionally NOT detected here anymore — they either have their own
    dedicated handling elsewhere (paper_empty via check_paper_status() /
    printer_health_worker(), offline via heartbeat staleness) or are left
    to manual/maintainer handling (cover_open), per the module docstring.
    """
    try:
        cmd = ["lpstat", "-p"]
        if PRINTER_NAME:
            cmd = ["lpstat", "-p", PRINTER_NAME, "-l"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = (result.stdout + result.stderr).lower()

        reasons = set()

        # paper_jam
        if any(k in output for k in ["media-jam", "paper-jam", "jammed", "jam"]):
            reasons.add("paper_jam")

        # toner_replace
        if any(k in output for k in [
            "toner low", "toner near end", "toner end", "toner-empty",
            "replace toner", "no toner", "toner empty",
        ]):
            reasons.add("toner_replace")

        return reasons

    except Exception as e:
        logger.debug(f"CUPS reason check error: {e}")
        return set()


def _update_debounce(incident_type: str) -> bool:
    """
    Increment the debounce counter for incident_type.
    Returns True if the threshold has been breached and we should report.
    Resets the counter after reporting (caller must handle the side-effect).
    """
    global _debounce_counters
    now = time.time()

    if incident_type not in _debounce_counters:
        _debounce_counters[incident_type] = {"count": 0, "first_seen_ts": now}

    entry = _debounce_counters[incident_type]
    entry["count"] += 1
    threshold = DEBOUNCE_THRESHOLDS.get(incident_type, 3)

    if entry["count"] >= threshold:
        logger.warning(
            f"Debounce [{incident_type}]: count {entry['count']} >= "
            f"{threshold} threshold — BREACH"
        )
        return True

    logger.debug(
        f"Debounce [{incident_type}]: {entry['count']}/{threshold} hits"
    )
    return False


def _reset_debounce(incident_type: str = None):
    """Clear one or all debounce counters (call after reporting or after error clears)."""
    global _debounce_counters
    if incident_type:
        _debounce_counters.pop(incident_type, None)
    else:
        _debounce_counters.clear()


def report_printer_incident(incident_type: str, triggered_by_job_id: str = None) -> bool:
    """
    POST to the report-printer-incident Edge Function.
    Returns True on success, False on any failure.
    We do NOT call the RPC directly — the Edge Function is the entry point.

    IMPORTANT: incident_type must be one of the values in
    kiosk_incident_type_enum. "toner_replace" requires the Postgres
    migration `ALTER TYPE kiosk_incident_type_enum ADD VALUE 'toner_replace'`
    to have been applied on the Supabase side — this has already been done
    as of this revision (confirmed via live enum check). If this function
    is ever called with an incident_type not present in the enum, the Edge
    Function call will fail with a database error.

    Only "paper_jam" and "toner_replace" should ever be passed here — see
    module docstring for why cover_open/offline/paper_empty/printer_error
    are excluded from this path.
    """
    if not REPORT_INCIDENT_URL:
        logger.error("REPORT_INCIDENT_URL not configured")
        return False

    payload = {
        "printer_id":    PRINTER_ID,
        "incident_type": incident_type,
    }
    if triggered_by_job_id:
        payload["triggered_by_job_id"] = triggered_by_job_id

    try:
        resp = requests.post(
            REPORT_INCIDENT_URL,
            json=payload,
            headers={
                "Content-Type":      "application/json",
                "Authorization":     f"Bearer {SUPABASE_SERVICE_ROLE}",
                "apikey":            SUPABASE_SERVICE_ROLE,
                "x-internal-secret": KIOSK_INCIDENT_INTERNAL_SECRET,
            },
            timeout=30,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            logger.warning(
                f"Incident reported [{incident_type}]: "
                f"jobs_cancelled={data.get('jobs_cancelled', '?')} "
                f"total_refunded={data.get('total_refunded', '?')}"
            )
            return True
        else:
            logger.error(
                f"report-printer-incident HTTP {resp.status_code}: {resp.text[:300]}"
            )
            return False
    except Exception as e:
        logger.error(f"report_printer_incident exception: {e}")
        return False


def _set_paused(paused: bool):
    """
    Thread-safe write of the INCIDENT_PAUSED flag.

    Also maintains the global current_status variable so that
    heartbeat_worker() (which writes printers.status = current_status every
    HEARTBEAT_INTERVAL seconds, unconditionally) correctly reflects the
    incident state instead of silently overwriting it back to "online".
    """
    global INCIDENT_PAUSED, current_status
    with incident_paused_lock:
        INCIDENT_PAUSED = paused
    if paused:
        current_status = "offline"
        logger.warning("Agent entering INCIDENT_PAUSED state — job polling suspended")
    else:
        current_status = "online"
        logger.info("Agent INCIDENT_PAUSED cleared — job polling resumed")


def _is_paused() -> bool:
    """Thread-safe read of the INCIDENT_PAUSED flag."""
    with incident_paused_lock:
        return INCIDENT_PAUSED


def _check_open_incident() -> dict | None:
    """
    Query kiosk_incidents for an open or test_page_pending incident on this printer.
    Returns the incident row dict, or None if no active incident exists.
    Uses service-role client so RLS does not block us.
    """
    try:
        res = (
            supabase.table("kiosk_incidents")
            .select(
                "id, printer_id, branch_id, incident_type, status, "
                "test_page_job_id, test_page_result, detected_at"
            )
            .eq("printer_id", PRINTER_ID)
            .in_("status", ["open", "test_page_pending"])
            .order("detected_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        logger.warning(f"_check_open_incident error: {e}")
        return None


def _check_printer_incident_status() -> str:
    """
    Read printers.incident_status for this printer.
    Returns 'available' | 'maintenance' | 'unknown'.
    """
    try:
        res = (
            supabase.table("printers")
            .select("incident_status")
            .eq("id", PRINTER_ID)
            .single()
            .execute()
        )
        if res.data:
            return res.data.get("incident_status") or "available"
        return "unknown"
    except Exception as e:
        logger.warning(f"_check_printer_incident_status error: {e}")
        return "unknown"


def handle_test_page(incident: dict) -> bool:
    """
    Print the test-page job from the incident, wait for REAL CUPS completion,
    then call confirm-test-page-result.

    This is the trust-critical path:
      - We use wait_for_job_completion() which polls lpstat -W not-completed
        until the job disappears from the not-completed list.
      - We do NOT use a timeout guess.
      - We then call confirm-test-page-result with the real outcome.

    Returns True if test page was sent to CUPS (result reported),
    False on fatal failure (incident not actionable).
    """
    incident_id  = incident.get("id")
    test_page_job_id = incident.get("test_page_job_id")

    if not incident_id or not test_page_job_id:
        logger.error(
            f"handle_test_page: missing incident_id={incident_id} "
            f"or test_page_job_id={test_page_job_id}"
        )
        return False

    logger.info(
        f"[TEST PAGE] Starting test-page print for incident {incident_id}, "
        f"job {test_page_job_id}"
    )

    # 1. Fetch the test-page job from print_jobs
    try:
        job_res = (
            supabase.table("print_jobs")
            .select("*")
            .eq("id", test_page_job_id)
            .single()
            .execute()
        )
        if not job_res.data:
            logger.error(f"[TEST PAGE] Job {test_page_job_id} not found in print_jobs")
            return False
        test_job = job_res.data
    except Exception as e:
        logger.error(f"[TEST PAGE] Failed to fetch test-page job: {e}")
        return False

    # 2. Get the file URL
    files = test_job.get("files") or []
    if not files:
        logger.error("[TEST PAGE] Test-page job has no files")
        _report_test_page_result(incident_id, test_page_job_id, "failed")
        return True

    file_info    = files[0]
    full_path    = file_info.get("url") or ""
    file_name    = str(file_info.get("name") or "test_page.pdf")
    storage_path = (
        full_path.split("print-files/")[-1]
        if "print-files/" in full_path
        else full_path
    )

    if not storage_path:
        logger.error("[TEST PAGE] Empty storage path")
        _report_test_page_result(incident_id, test_page_job_id, "failed")
        return True

    file_url = _get_signed_url(storage_path)
    if not file_url:
        logger.error("[TEST PAGE] Could not get signed URL for test page")
        _report_test_page_result(incident_id, test_page_job_id, "failed")
        return True

    ext       = Path(file_name).suffix.lower() or ".pdf"
    temp_file = os.path.join(
        tempfile.gettempdir(), f"vprint_testpage_{test_page_job_id}{ext}"
    )

    # 3. Download
    try:
        _update_job_status(test_page_job_id, "downloading")
        download_file(file_url, temp_file)
    except Exception as e:
        logger.error(f"[TEST PAGE] Download failed: {e}")
        _report_test_page_result(incident_id, test_page_job_id, "failed")
        return True

    # 4. Convert / normalize (same pipeline as normal jobs)
    _update_job_status(test_page_job_id, "processing")
    original_temp   = temp_file
    pdf_orientation = "portrait"
    converted_file  = None
    cups_job_id     = None
    cups_success    = False

    try:
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
            converted_file = convert_image_to_pdf(temp_file)
            temp_file = converted_file
        elif ext in (".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"):
            converted_file = convert_office_to_pdf(original_temp)
            if converted_file != original_temp:
                pdf_orientation, _ = _analyze_pdf(converted_file)
                temp_file = normalize_pdf_to_a4(converted_file, pdf_orientation)
            else:
                temp_file = converted_file
        elif ext == ".pdf":
            pdf_orientation, _ = _analyze_pdf(temp_file)
            temp_file = normalize_pdf_to_a4(temp_file, pdf_orientation)

        # 5. Print — simplex B&W, single copy (test page)
        _update_job_status(test_page_job_id, "printing")
        logger.info("[TEST PAGE] Sending to CUPS...")
        cups_job_id = print_file(
            file_path       = str(temp_file),
            copies          = 1,
            color_type      = "bw",
            double_sided    = False,
            pdf_orientation = pdf_orientation,
        )

        if cups_job_id:
            # 6. REAL CUPS completion — poll lpstat until job leaves not-completed list
            logger.info(
                f"[TEST PAGE] CUPS job {cups_job_id} submitted — "
                "waiting for physical completion..."
            )
            cups_success = job_tracking_worker(test_page_job_id, cups_job_id)
            logger.info(
                f"[TEST PAGE] CUPS completion result: {'success' if cups_success else 'failed'}"
            )

            # ── SNMP physical check for test page (branch 6 pilot only) ──────
            # A false "success" here would unblock the printer from maintenance
            # mode — so we must verify the page actually came out.
            # No-op (returns True immediately) when SNMP_ENABLED=false.
            # Test pages are always simplex/single-copy, so expected sides = 1
            # regardless of the duplex conversion used for normal jobs.
            if cups_success:
                _tp_verified, _tp_pages, _tp_matched_type = verify_print_via_snmp(1, [])
                if not _tp_verified:
                    logger.warning(
                        "[TEST PAGE] SNMP: test page did NOT physically print "
                        f"(confirmed {_tp_pages}/1 pages, "
                        f"classified as: {_tp_matched_type or 'unclassified'}) "
                        "— overriding cups_success=False"
                    )
                    cups_success = False
                elif SNMP_ENABLED and SNMP_HOST:
                    logger.info(
                        "[TEST PAGE] SNMP: test page physically confirmed via page counter"
                    )
        else:
            # lp returned no job ID — spooler accepted but we can't track
            # Wait a generous fallback and assume it printed
            logger.warning(
                "[TEST PAGE] No CUPS job ID returned — "
                "waiting 30s as fallback..."
            )
            time.sleep(30)
            cups_success = True   # optimistic — operator can retry if needed

    except Exception as e:
        logger.error(f"[TEST PAGE] Print exception: {e}")
        cups_success = False
    finally:
        # Clean up temp files
        files_to_clean = {original_temp}
        if converted_file and converted_file != original_temp:
            files_to_clean.add(converted_file)
        if temp_file != original_temp and temp_file != converted_file:
            files_to_clean.add(temp_file)
        _cleanup(*files_to_clean)

    # 7. Report result to Supabase via confirm-test-page-result edge function
    result_str = "success" if cups_success else "failed"
    _report_test_page_result(incident_id, test_page_job_id, result_str)
    return True


def _report_test_page_result(incident_id: str, job_id: str, result: str):
    """
    Call confirm-test-page-result edge function.
    result: 'success' | 'failed'
    """
    if not CONFIRM_TEST_PAGE_URL:
        logger.error("CONFIRM_TEST_PAGE_URL not configured")
        return

    payload = {
        "incident_id":    incident_id,
        "job_id":         job_id,
        "test_page_result": result,
    }
    try:
        resp = requests.post(
            CONFIRM_TEST_PAGE_URL,
            json=payload,
            headers={
                "Content-Type":      "application/json",
                "Authorization":     f"Bearer {SUPABASE_SERVICE_ROLE}",
                "apikey":            SUPABASE_SERVICE_ROLE,
                "x-internal-secret": KIOSK_INCIDENT_INTERNAL_SECRET,
            },
            timeout=30,
        )
        if resp.status_code in (200, 201):
            logger.info(
                f"[TEST PAGE] confirm-test-page-result: {result} "
                f"(incident {incident_id})"
            )
        else:
            logger.error(
                f"confirm-test-page-result HTTP {resp.status_code}: "
                f"{resp.text[:300]}"
            )
    except Exception as e:
        logger.error(f"_report_test_page_result exception: {e}")


def incident_monitor_worker():
    """
    Background thread that runs ONLY while INCIDENT_PAUSED is True.
    Polls kiosk_incidents for a test_page_pending signal.
    When found, drives the test-page print flow.

    This thread stays alive forever but sleeps most of the time when
    not paused — it wakes on INCIDENT_POLL_INTERVAL to re-check.
    """
    logger.info("Incident monitor thread started")
    while True:
        try:
            if not _is_paused():
                time.sleep(INCIDENT_POLL_INTERVAL)
                continue

            incident = _check_open_incident()

            if incident is None:
                # No open incident — this can happen if the incident was
                # resolved externally without a test page (e.g., admin override).
                # Clear paused so normal operation can resume.
                logger.info(
                    "Incident monitor: no open incident found — clearing paused state"
                )
                _reset_debounce()
                _set_paused(False)
                time.sleep(INCIDENT_POLL_INTERVAL)
                continue

            status = incident.get("status")

            if status == "open":
                # Incident reported but test page not yet triggered — keep waiting
                logger.debug(
                    f"Incident monitor: incident {incident['id']} is 'open' — "
                    "waiting for test-page trigger..."
                )

            elif status == "test_page_pending":
                # Test-page trigger received — print it
                if incident.get("test_page_job_id"):
                    logger.info(
                        f"Incident monitor: test_page_pending detected — "
                        f"handling test page for incident {incident['id']}"
                    )
                    handle_test_page(incident)
                    logger.info(
                        "Incident monitor: test page result reported — "
                        "will re-check incident status next poll."
                    )
                else:
                    logger.warning(
                        "Incident monitor: test_page_pending but no test_page_job_id yet"
                    )

        except Exception as e:
            logger.error(f"incident_monitor_worker error: {e}")

        time.sleep(INCIDENT_POLL_INTERVAL)


def check_and_report_cups_errors():
    """
    Called from the main polling loop (when NOT paused) to check CUPS for
    error-state reasons and advance debounce counters.

    Only paper_jam and toner_replace are checked (see
    _get_cups_error_reasons() and module docstring for why cover_open /
    offline / paper_empty / printer_error are excluded).

    If a threshold is breached:
      1. Calls report_printer_incident() -> Edge Function.
      2. Resets that error's debounce counter.
      3. Sets INCIDENT_PAUSED = True (via _set_paused, which also updates
         current_status so heartbeat_worker reflects it correctly).
      4. For toner_replace, additionally queues a Telegram alert via the
         existing send_alert()/insert_telegram_alert() pipeline.

    Non-error poll: clears the counter for any error type that has cleared.
    """
    if _is_paused():
        return  # Already paused — don't double-report

    active_errors = _get_cups_error_reasons()

    # Clear counters for errors that have cleared
    for etype in list(_debounce_counters.keys()):
        if etype not in active_errors:
            if _debounce_counters[etype]["count"] > 0:
                logger.debug(f"Debounce [{etype}]: error cleared — resetting counter")
            _reset_debounce(etype)

    # Advance counters for active errors
    for etype in active_errors:
        breached = _update_debounce(etype)
        if breached:
            logger.warning(
                f"INCIDENT THRESHOLD BREACHED: {etype} — "
                f"reporting incident and entering paused state"
            )
            # Reset before setting paused so the counter is clean on resume
            _reset_debounce(etype)

            # Report to Supabase via Edge Function
            success = report_printer_incident(etype)
            if success:
                _set_paused(True)
                if etype == "toner_replace":
                    send_alert(
                        alert_type="toner_replace",
                        alert_level="critical",
                        value="toner_replace",
                        ntfy_title="Toner Replacement Needed",
                        ntfy_msg=(
                            "Printer toner needs replacement. "
                            "Printer paused until resolved."
                        ),
                        priority="urgent",
                        tags=["warning", "printer"],
                    )
            else:
                logger.error(
                    f"report_printer_incident failed for {etype} — "
                    "will retry on next poll cycle"
                )
            # Only report one incident type per poll cycle
            break


# ========================================================================
# MAIN LOOP
# ========================================================================

def main():
    global supabase
    logger.info("=" * 60)
    logger.info("   VPrint Raspberry Pi Agent — Starting")
    logger.info(f"   PRINTER_ID   : {PRINTER_ID}")
    logger.info(f"   PRINTER_NAME : {PRINTER_NAME or '(default CUPS printer)'}")
    logger.info(f"   BRANCH_ID    : {BRANCH_ID or '(not set)'}")
    logger.info(f"   POLL_INTERVAL: {POLL_INTERVAL}s")
    logger.info(f"   HEARTBEAT    : {HEARTBEAT_INTERVAL}s")
    logger.info(f"   TG_POLL      : {TELEGRAM_ALERT_POLL_INTERVAL}s")
    logger.info(f"   ETA_DB_WRITE : every {ETA_DB_WRITE_INTERVAL_SECS}s (local countdown every 1s)")
    logger.info(f"   LOG_LEVEL    : {_LOG_LEVEL_STR}")
    logger.info(f"   GS_AVAILABLE : {GS_AVAILABLE}")
    logger.info(f"   LO_AVAILABLE : {LO_AVAILABLE}")
    logger.info(f"   SNMP_ENABLED : {SNMP_ENABLED}")
    logger.info(f"   SNMP_HOST    : {SNMP_HOST or '(not set — SNMP disabled)'}")
    logger.info("=" * 60)

    # -- Auto-detect default printer if PRINTER_NAME not set -------
    if not PRINTER_NAME:
        default_printer = _detect_default_printer()
        if default_printer:
            logger.info(f"Auto-detected default printer: {default_printer}")
        else:
            logger.warning(
                "PRINTER_NAME not set and no default printer detected. "
                "Jobs will go to CUPS default."
            )

    # -- List available printers -----------------------------------
    get_available_printers()

    # -- Crash recovery: reset stuck jobs -------------------------
    recover_stuck_jobs()

    # ── Phase 3: Boot-time incident_status check ─────────────────
    # CRITICAL: If the printer is already in 'maintenance' due to a
    # pre-crash incident, we must NOT default back to 'available'.
    # Enter INCIDENT_PAUSED immediately so the incident_monitor_worker
    # takes over — it will wait for the test-page trigger.
    incident_status_on_boot = _check_printer_incident_status()
    if incident_status_on_boot == "maintenance":
        open_incident = _check_open_incident()
        if open_incident:
            logger.warning(
                f"BOOT RECOVERY: printer is in maintenance mode "
                f"(incident {open_incident['id']}, status={open_incident['status']}) — "
                "entering INCIDENT_PAUSED without re-reporting"
            )
            _set_paused(True)
        else:
            logger.warning(
                "BOOT: printer.incident_status=maintenance but no open incident found — "
                "may have been resolved already. Starting normally."
            )
    else:
        logger.info(
            f"BOOT: printer.incident_status={incident_status_on_boot} — normal start"
        )

    # -- Background threads ---------------------------------------
    threading.Thread(
        target=heartbeat_worker, daemon=True, name="heartbeat"
    ).start()
    # NOTE: eta_countdown_worker has been removed. ETA countdown now runs
    # inside job_tracking_worker, scoped to each active CUPS job.
    threading.Thread(
        target=printer_health_worker, daemon=True, name="printer_health"
    ).start()
    threading.Thread(
        target=dispatch_telegram_alerts_worker, daemon=True, name="tg_dispatcher"
    ).start()
    # ── Phase 3: Incident monitor thread ─────────────────────────
    threading.Thread(
        target=incident_monitor_worker, daemon=True, name="incident_monitor"
    ).start()

    logger.info(
        f"Polling every {POLL_INTERVAL}s for "
        f"queued+paid jobs on printer {PRINTER_ID}"
    )

    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 10

    while True:
        try:
            # ── Phase 3: If paused due to incident, skip job polling ──
            if _is_paused():
                # Don't log every 3 s — would flood the log
                time.sleep(POLL_INTERVAL)
                continue

            # ── Phase 3: Check CUPS for error conditions each poll ────
            # This runs before polling for jobs so that if an error fires
            # mid-cycle, we enter paused state before claiming a new job.
            check_and_report_cups_errors()

            # If check_and_report_cups_errors() set paused, skip this cycle
            if _is_paused():
                time.sleep(POLL_INTERVAL)
                continue

            # -- Poll for next queued+paid job --------------------
            # Exclude test-page jobs — those are handled by the incident monitor
            response = (
                supabase.table("print_jobs")
                .select("*")
                .eq("printer_id",     PRINTER_ID)
                .eq("status",         "queued")
                .eq("payment_status", "paid")
                .eq("is_test_page",   False)
                .order("created_at",  desc=False)
                .limit(1)
                .execute()
            )

            consecutive_errors = 0  # Reset on success

            if response.data and len(response.data) > 0:
                candidate = response.data[0]
                job_id    = candidate.get("id")

                # Atomic lock: flip queued -> printing (prevents duplicate processing)
                update_res = (
                    supabase.table("print_jobs")
                    .update({
                        "status":     "printing",
                        "started_at": _now_utc(),
                    })
                    .eq("id",             job_id)
                    .eq("status",         "queued")
                    .eq("payment_status", "paid")
                    .execute()
                )

                if update_res.data and len(update_res.data) > 0:
                    logger.info(f"Locked job {job_id} -> printing")
                    full_job = update_res.data[0]

                    # -- Wait for backend duplex_mode --------------
                    if not full_job.get("duplex_mode"):
                        logger.info(
                            "duplex_mode not set yet — "
                            f"waiting up to {DUPLEX_MODE_WAIT_MAX}s for backend ..."
                        )
                        checks = DUPLEX_MODE_WAIT_MAX // 2
                        for attempt in range(checks):
                            time.sleep(2)
                            try:
                                refresh = (
                                    supabase.table("print_jobs")
                                    .select("duplex_mode")
                                    .eq("id", job_id)
                                    .single()
                                    .execute()
                                )
                                if refresh.data and refresh.data.get("duplex_mode"):
                                    full_job["duplex_mode"] = refresh.data["duplex_mode"]
                                    logger.info(
                                        f"duplex_mode resolved after {(attempt+1)*2}s: "
                                        f"{full_job['duplex_mode']}"
                                    )
                                    break
                                logger.info(f"  poll {attempt+1}/{checks}: still waiting ...")
                            except Exception as poll_err:
                                logger.warning(f"duplex_mode poll error: {poll_err}")
                        else:
                            logger.warning(
                                f"duplex_mode not resolved after {DUPLEX_MODE_WAIT_MAX}s "
                                "— will auto-detect locally from PDF"
                            )

                    process_job(full_job)
                else:
                    logger.warning(
                        f"Job {job_id} already claimed by another agent — skipping"
                    )

        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Polling error (#{consecutive_errors}): {e}")

            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.critical(
                    f"Too many consecutive errors ({consecutive_errors}). "
                    "Attempting Supabase reconnect..."
                )
                try:
                    supabase = _create_supabase_client()
                    consecutive_errors = 0
                    logger.info("Supabase reconnected successfully")
                except Exception as rc_err:
                    logger.error(f"Reconnect failed: {rc_err}")

            # Exponential backoff, max 30s
            sleep_time = min(POLL_INTERVAL * (2 ** min(consecutive_errors, 4)), 30)
            time.sleep(sleep_time)
            continue

        time.sleep(POLL_INTERVAL)


# ========================================================================
# ENTRY POINT
# ========================================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Agent stopped by user (Ctrl+C)")
    except Exception as fatal:
        logger.critical(f"FATAL CRASH: {fatal}", exc_info=True)
        sys.exit(1)
