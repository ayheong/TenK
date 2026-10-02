from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]

# The EDGAR client reads SEC_USER_AGENT when it is imported, so the environment
# has to be loaded before any other app.api module imports it.
load_dotenv(REPO_ROOT / ".env")
