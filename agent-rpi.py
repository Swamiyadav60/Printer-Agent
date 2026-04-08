#!/usr/bin/env python3
"""
VPrint Printer Agent - Cross-Platform
Supports: Windows, Linux (Raspberry Pi), macOS
Supports: PDF, Images, DOCX, PPTX
"""

import os
import sys
import time
import tempfile
import subprocess
import logging
import uuid
import io
import threading
import platform
from pathlib import Path

import requests
from PIL import Image
from dotenv import load_dotenv
from supabase import create_client


# -------------------------
# Platform Detection
# -------------------------
SYSTEM = platform.system()  # "Windows", "Linux", "Darwin"
IS_WINDOWS = SYSTEM == "Windows"
IS_LINUX = SYSTEM == "Linux"
IS_MACOS = SYSTEM == "Darwin"

# Import platform-specific modules only when needed
if IS_WINDOWS:
    import win32print
    import win32com.client


# -------------------------
# Logging
# -------------------------
os.makedirs("logs", exist_ok=True)

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler("logs/agent.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


# -------------------------
# ENV
# -------------------------
load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")
PRINTER_ID = os.getenv("PRINTER_ID")
PRINTER_NAME = os.getenv("PRINTER_NAME")

POLL_INTERVAL = 3
HEARTBEAT_INTERVAL = 5

# Global status tracking
current_status = "online"

if not all([SUPABASE_URL, SUPABASE_SERVICE_ROLE, PRINTER_ID]):
    logger.error("Missing required ENV variables: SUPABASE_URL, SUPABASE_SERVICE_ROLE, PRINTER_ID")
    sys.exit(1)

logger.info(f"Starting VPrint Agent on {SYSTEM} (Python {sys.version_info.major}.{sys.version_info.minor})")
logger.info(f"PRINTER_ID: {PRINTER_ID}")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)


# -------------------------
# FILE CONVERSIONS
# -------------------------

def convert_image_to_pdf(path):
    """Convert image to PDF using PIL (cross-platform)"""
    try:
        img = Image.open(path)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        pdf_path = path + ".pdf"
        img.save(pdf_path, "PDF", resolution=100)
        logger.info(f"Image converted: {path} → {pdf_path}")
        return pdf_path

    except Exception as e:
        logger.error(f"Image conversion error: {e}")
        return path


def convert_docx_to_pdf(path):
    """Convert DOCX to PDF using Pandoc (cross-platform, lightweight)"""
    try:
        pdf_path = path + ".pdf"
        
        # Use pandoc to convert DOCX to PDF
        cmd = ["pandoc", path, "-o", pdf_path]
        logger.info(f"Running: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        logger.info(f"DOCX converted: {path} → {pdf_path}")
        return pdf_path

    except FileNotFoundError:
        logger.error("Pandoc not found. Install with: sudo apt install pandoc")
        return path
    except subprocess.TimeoutExpired:
        logger.error(f"DOCX conversion timeout: {path}")
        return path
    except Exception as e:
        logger.error(f"DOCX conversion failed: {e}")
        return path


def convert_pptx_to_pdf(path):
    """Convert PPTX to PDF using Pandoc (cross-platform, lightweight)"""
    try:
        pdf_path = path + ".pdf"
        
        # Use pandoc to convert PPTX to PDF
        cmd = ["pandoc", path, "-o", pdf_path]
        logger.info(f"Running: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        logger.info(f"PPTX converted: {path} → {pdf_path}")
        return pdf_path

    except FileNotFoundError:
        logger.error("Pandoc not found. Install with: sudo apt install pandoc")
        return path
    except subprocess.TimeoutExpired:
        logger.error(f"PPTX conversion timeout: {path}")
        return path
    except Exception as e:
        logger.error(f"PPTX conversion failed: {e}")
        return path


# -------------------------
# HEARTBEAT
# -------------------------
def heartbeat_worker():
    """Update printer status in database every HEARTBEAT_INTERVAL seconds"""
    logger.info("Heartbeat started")

    while True:
        try:
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            
            supabase.table("printers").update({
                "status": current_status,
                "last_seen": timestamp
            }).eq("id", PRINTER_ID).execute()

        except Exception as e:
            logger.warning(f"Heartbeat error: {e}")

        time.sleep(HEARTBEAT_INTERVAL)


# -------------------------
# Printer Detection
# -------------------------
def get_available_printers():
    """List available printers based on OS"""
    try:
        if IS_WINDOWS:
            printers = win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL |
                win32print.PRINTER_ENUM_CONNECTIONS
            )
            printer_names = [p[2] for p in printers]
            logger.info("Available printers: " + ", ".join(printer_names))

        elif IS_LINUX or IS_MACOS:
            # Use lpstat to list printers (CUPS)
            result = subprocess.run(["lpstat", "-p", "-d"], capture_output=True, text=True, timeout=5)
            logger.info(f"CUPS Printers:\n{result.stdout}")

    except Exception as e:
        logger.warning(f"Printer detection error: {e}")


# -------------------------
# PRINT
# -------------------------
def print_file(file_path, copies=1, start_page=None, end_page=None, color_type="bw"):
    """Print file using appropriate OS command"""
    
    try:
        if IS_WINDOWS:
            print_file_windows(file_path, copies, start_page, end_page, color_type)
        elif IS_LINUX or IS_MACOS:
            print_file_cups(file_path, copies, start_page, end_page, color_type)
        else:
            raise Exception(f"Unsupported OS: {SYSTEM}")
            
    except Exception as e:
        logger.error(f"Print failed: {e}")
        raise


def print_file_windows(file_path, copies=1, start_page=None, end_page=None, color_type="bw"):
    """Windows printer using SumatraPDF"""
    sumatra = r"C:\print_tools\sumatraPDF.exe"

    if not os.path.exists(sumatra):
        sumatra = "SumatraPDF.exe"

    color_setting = "color" if color_type == "color" else "monochrome"
    settings = f"{copies}x,fit,shrink,{color_setting}"

    if start_page and end_page:
        settings += f",{start_page}-{end_page}"
    settings += ",paper=A4"

    cmd = [
        sumatra,
        "-print-to",
        PRINTER_NAME if PRINTER_NAME else "default",
        "-print-settings",
        settings,
        "-silent",
        "-exit-on-print",
        file_path
    ]

    logger.info(f"Windows print command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, timeout=120)


def print_file_cups(file_path, copies=1, start_page=None, end_page=None, color_type="bw"):
    """Linux/macOS printer using CUPS (lp command)"""
    
    cmd = ["lp"]
    
    # Add printer name
    if PRINTER_NAME:
        cmd.extend(["-d", PRINTER_NAME])
    
    # Add copies
    cmd.extend(["-n", str(copies)])
    
    # Add color mode
    if color_type == "color":
        cmd.extend(["-o", "ColorModel=CMYK"])
    else:
        cmd.extend(["-o", "ColorModel=Gray"])
    
    # Add page range if specified
    if start_page and end_page:
        cmd.extend(["-P", f"{start_page}-{end_page}"])
    
    # Add media (paper size)
    cmd.extend(["-o", "media=A4"])
    
    # Add file
    cmd.append(file_path)
    
    logger.info(f"CUPS print command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, timeout=120)


# -------------------------
# Helpers
# -------------------------
def download_file(url, path):
    """Downloads a file from a URL to a local path."""
    logger.info(f"Downloading file to {path}")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(r.content)


# -------------------------
# Process Job
# -------------------------
def process_job(job):
    """Process a single print job"""
    global current_status
    job_id = job.get("id")
    if not job_id:
        return

    # SAFETY CHECK: Only process if paid
    if job.get("payment_status") != "paid":
        logger.warning(f"Aborting Job {job_id}: Payment status is {job.get('payment_status')}")
        return

    logger.info(f"Starting Job {job_id}")
    current_status = "busy"

    temp_file = None

    try:
        # 1. Determine the download URL
        storage_path = job.get("file_path")
        file_name = "document.pdf"
        file_url = None

        if not storage_path:
            files = job.get("files", [])
            if not files:
                raise Exception("No file data found in job")
            
            file_info = files[0]
            storage_path = file_info.get("url")
            file_name = str(file_info.get("name") or "document.pdf")

        if not storage_path:
            raise Exception("Storage path missing in job info")

        bucket_name = "print-files"
        clean_path = storage_path

        logger.info(f"Generating signed URL for bucket: {bucket_name}, path: {clean_path}")
        
        # Get signed URL from Supabase
        try:
            signed_res = supabase.storage.from_(bucket_name).create_signed_url(clean_path, 60)
            
            # Handle various return types from supabase-py versions
            if isinstance(signed_res, dict):
                file_url = signed_res.get("signedURL") or signed_res.get("signed_url") or signed_res.get("signedUrl")
            elif isinstance(signed_res, str):
                file_url = signed_res
            else:
                file_url = getattr(signed_res, 'data', {}).get('signedUrl') or getattr(signed_res, 'signed_url', None)
                
            if not file_url and hasattr(signed_res, 'signed_url'):
                file_url = signed_res.signed_url
        except Exception as e:
            logger.error(f"Supabase storage error: {e}")
            raise Exception(f"Failed to generate signed URL: {e}")

        if not file_url:
            logger.error(f"Signed URL response: {signed_res}")
            raise Exception("Failed to generate download URL (empty result)")

        logger.info(f"Download URL generated successfully")

        # 2. Download to a local temporary path
        ext = Path(file_name).suffix or ".pdf"
        temp_file = os.path.join(
            tempfile.gettempdir(),
            f"vprint_{job_id}{ext}"
        )

        download_file(file_url, temp_file)

        # 3. Handle conversions and parameters
        copies = int(job.get("copies") or 1)
        color_type = job.get("color_type") or "bw"
        start_page = job.get("start_page")
        end_page = job.get("end_page")

        # Use lowercase extension for type checking
        check_ext = Path(temp_file).suffix.lower()

        if check_ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
            temp_file = convert_image_to_pdf(temp_file)
        elif check_ext == ".docx":
            temp_file = convert_docx_to_pdf(temp_file)
        elif check_ext == ".pptx":
            temp_file = convert_pptx_to_pdf(temp_file)

        # 4. Final Print
        print_file(str(temp_file), copies, start_page, end_page, color_type)

        # 5. Mark job as completed via RPC
        logger.info("Completing job via complete_print_job RPC")
        try:
            result = supabase.rpc("complete_print_job", {
                "p_job_id":     job_id,
                "p_user_id":    job.get("user_id"),
                "p_pages":      job.get("pages_to_print") or job.get("total_pages") or job.get("pages") or 1,
                "p_amount":     float(job.get("total_price") or job.get("amount") or 0),
                "p_printer_id": job.get("printer_id"),
                "p_branch_id":  job.get("branch_id"),
                "p_file_name":  job.get("file_name")
            }).execute()
            logger.info(f"Job {job_id} completed successfully: {result.data}")
        except Exception as e:
            logger.error(f"Job completion RPC failed: {e}")
            # Fallback: at minimum mark the job done
            supabase.table("print_jobs").update({
                "status": "completed"
            }).eq("id", job_id).execute()

    except Exception as e:
        logger.error(f"Job failed: {e}")
        try:
            supabase.table("print_jobs").update({
                "status": "failed",
                "error_message": str(e)[:500]
            }).eq("id", job_id).execute()
        except:
            pass

    finally:
        current_status = "online"
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass


# -------------------------
# Main Loop
# -------------------------
def main():
    logger.info(f"VPrint Agent Started on {SYSTEM}")
    get_available_printers()

    # Start heartbeat thread
    hb_thread = threading.Thread(target=heartbeat_worker, daemon=True)
    hb_thread.start()

    while True:
        try:
            # Fetch the candidate job
            response = supabase.table("print_jobs") \
                .select("*") \
                .eq("printer_id", PRINTER_ID) \
                .eq("status", "queued") \
                .order("created_at", desc=False) \
                .limit(1) \
                .execute()

            if response.data and len(response.data) > 0:
                candidate_job = response.data[0]
                job_id = candidate_job.get("id")
                
                if candidate_job.get("payment_status") != "paid":
                    logger.warning(f"Aborting Job {job_id}: Payment status is {candidate_job.get('payment_status')}")
                    supabase.table("print_jobs").update({"status": "failed", "error_message": "Unpaid job in queue"}).eq("id", job_id).execute()
                    continue

                # Claim the job by moving it to 'printing'
                update_res = supabase.table("print_jobs").update({
                    "status": "printing"
                }).eq("id", job_id) \
                  .eq("status", "queued") \
                  .eq("payment_status", "paid") \
                  .execute()
                
                if update_res.data and len(update_res.data) > 0:
                    logger.info(f"Claimed Job {job_id}. Starting print...")
                    process_job(update_res.data[0])
                else:
                    logger.warning(f"Job {job_id} was already picked up by another agent.")

        except Exception as e:
            logger.error(f"Polling error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
        sys.exit(0)
