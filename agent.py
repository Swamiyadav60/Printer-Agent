import os
import sys
import time
import tempfile
import subprocess
import logging
import uuid
import io
from pathlib import Path

import requests
from dotenv import load_dotenv
from supabase import create_client

# -------------------------
# Logging Configuration
# -------------------------
os.makedirs("logs", exist_ok=True)

# Ensure Windows stdout uses UTF-8 to prevent crashes with non-ASCII characters
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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
# Environment Configuration
# -------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")
PRINTER_ID = os.getenv("PRINTER_ID")
PRINTER_NAME = os.getenv("PRINTER_NAME")

# Primary and Fallback URLs
PRIMARY_DOMAIN = "smartprinter.in"
FALLBACK_DOMAIN = "smartprinter-five.vercel.app"

# Load base URL from env, default to smartprinter.in if not set
initial_base_url = os.getenv("BACKEND_API_URL", f"https://{PRIMARY_DOMAIN}/api/jobs").rstrip("/")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL") or 3)

if not all([SUPABASE_URL, SUPABASE_SERVICE_ROLE, PRINTER_ID]):
    logger.error("Missing required environment variables (SUPABASE_URL, SUPABASE_SERVICE_ROLE, PRINTER_ID).")
    sys.exit(1)

# Initialize Supabase Client
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)

# -------------------------
# Dynamic API Manager
# -------------------------
class ApiManager:
    def __init__(self, base_url):
        self.base_url = base_url
        self.is_using_fallback = False
        logger.info(f"Initialized API Manager with: {self.base_url}")

    def get_url(self, path=""):
        """Returns the full URL for a given path."""
        url = self.base_url
        if path:
            url = f"{self.base_url}/{path}".replace("//api", "/api") # Clean double slashes
        return url

    def switch_to_fallback(self):
        """Switches the base URL to the Vercel fallback domain."""
        if not self.is_using_fallback:
            logger.warning(f"405 Detected on {PRIMARY_DOMAIN}. Switching to fallback: {FALLBACK_DOMAIN}")
            # Replace smartprinter.in with smartprinter-five.vercel.app
            if PRIMARY_DOMAIN in self.base_url:
                self.base_url = self.base_url.replace(PRIMARY_DOMAIN, FALLBACK_DOMAIN)
            else:
                # If the env was something else, force it to the known fallback
                self.base_url = f"https://{FALLBACK_DOMAIN}/api/jobs"
            
            self.is_using_fallback = True
            logger.info(f"New API Base URL: {self.base_url}")
            return True
        return False

api_manager = ApiManager(initial_base_url)

# Standard headers for API requests
api_headers = {
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE}",
    "apikey": SUPABASE_SERVICE_ROLE,
    "Content-Type": "application/json"
}

# -------------------------
# API Request Wrapper with Fallback Logic
# -------------------------
def safe_request(method, path, **kwargs):
    """Executes a request with automatic 405 fallback to vercel.app domain."""
    url = api_manager.get_url(path)
    logger.info(f"Sending {method} request to: {url}")
    
    try:
        response = requests.request(method, url, headers=api_headers, timeout=15, **kwargs)
        
        if response.status_code == 405:
            logger.error(f"HTTP 405 Method Not Allowed at {url}")
            logger.error(f"Response Body: {response.text[:1000]}")
            
            # Try switching to fallback if we haven't already
            if api_manager.switch_to_fallback():
                new_url = api_manager.get_url(path)
                logger.info(f"Retrying with fallback URL: {new_url}")
                return requests.request(method, new_url, headers=api_headers, timeout=15, **kwargs)
        
        return response
    except Exception as e:
        logger.error(f"Request failed to {url}: {e}")
        return None

# -------------------------
# Printing Logic
# -------------------------
def print_file(file_path, copies=1, start_page=None, end_page=None):
    """Prints a file using SumatraPDF with optional page range and copies."""
    sumatra_path = r"C:\print_tools\sumatraPDF.exe"
    if not os.path.exists(sumatra_path):
        sumatra_path = "SumatraPDF.exe"

    settings = f"{copies}x"
    if start_page and end_page:
        settings += f",{start_page}-{end_page}"

    logger.info(f"Printing: {file_path} | Copies: {copies} | Range: {start_page}-{end_page if start_page else 'All'}")

    cmd = [
        sumatra_path,
        "-print-to", PRINTER_NAME if PRINTER_NAME else "default",
        "-print-settings", settings,
        "-silent",
        file_path
    ]
    
    try:
        subprocess.run(cmd, check=True, timeout=120)
    except subprocess.CalledProcessError as e:
        raise Exception(f"SumatraPDF failed with exit code {e.returncode}")
    except Exception as e:
        raise Exception(f"Print subprocess error: {str(e)}")

# -------------------------
# Job Processing
# -------------------------
def process_job(job):
    """Handles the lifecycle of a single print job."""
    job_id = job.get("id")
    if not job_id:
        return

    logger.info(f"--- Starting Job: {job_id} ---")

    # 1. Mark as Processing
    resp = safe_request("POST", f"{job_id}/processing")
    if not resp or resp.status_code != 200:
        logger.error(f"Could not mark job {job_id} as processing. Skipping.")
        return

    temp_file = None
    try:
        # 2. Extract file info
        files = job.get("files", [])
        if not files or not isinstance(files, list):
            raise Exception("No printable files found in job data.")
        
        file_info = files[0]
        file_path_in_bucket = file_info.get("url")
        if not file_path_in_bucket:
            raise Exception("File URL missing in job data.")

        # 3. Get Signed URL from Supabase
        logger.info(f"Downloading file: {file_info.get('name', 'unnamed')}")
        signed_response = supabase.storage.from_("print-files").create_signed_url(
            file_path_in_bucket, 60
        )
        
        if isinstance(signed_response, dict):
            if "error" in signed_response:
                raise Exception(f"Supabase Storage Error: {signed_response['error']}")
            signed_url = signed_response.get("signedURL") or signed_response.get("signed_url")
        else:
            signed_url = signed_response

        if not signed_url:
            raise Exception("Failed to generate signed URL for download.")

        # 4. Download file
        r = requests.get(signed_url, timeout=60)
        r.raise_for_status()

        ext = Path(file_info.get("name", "doc.pdf")).suffix or ".pdf"
        temp_file = os.path.join(
            tempfile.gettempdir(),
            f"vprint_{uuid.uuid4()}{ext}"
        )

        with open(temp_file, "wb") as f:
            f.write(r.content)

        # 5. Extract print parameters
        copies = int(job.get("copies") or 1)
        start_page = job.get("start_page")
        end_page = job.get("end_page")

        # 6. Execute Print
        print_file(temp_file, copies, start_page, end_page)

        # 7. Mark as Completed
        safe_request("POST", f"{job_id}/completed")
        logger.info(f"--- Job {job_id} Completed Successfully ---")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id} Failed: {error_msg}")
        safe_request("POST", f"{job_id}/failed", json={"error_message": error_msg[:500]})

    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass

# -------------------------
# Main Execution Loop
# -------------------------
def main():
    logger.info("==========================================")
    logger.info(f"VPrint Agent Started | Printer: {PRINTER_ID}")
    logger.info("==========================================")

    while True:
        try:
            # Polling for new jobs
            response = safe_request("GET", f"?printer_id={PRINTER_ID}")
            
            if response and response.status_code == 200:
                job_data = response.json()
                if job_data and isinstance(job_data, dict) and job_data.get("id"):
                    process_job(job_data)
        
        except requests.exceptions.ConnectionError:
            logger.error("Connection error. Is the backend server running?")
        except Exception as e:
            logger.error(f"Polling loop error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Agent stopped by user.")
    except Exception as e:
        logger.critical(f"Agent crashed: {e}")
