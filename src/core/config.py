# src/core/config.py
from dotenv import load_dotenv
import os

load_dotenv()

JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_TOKEN = os.environ.get("JIRA_TOKEN") 
JIRA_BASE = os.environ.get("JIRA_BASE")
DEFAULT_PROJECT_KEY = os.environ.get("DEFAULT_PROJECT_KEY")
RELATES_LINK_TYPE = os.environ.get("RELATES_LINK_TYPE", "Relates")

CLICKUP_API_KEY = os.environ.get("CLICKUP_API_KEY")
CLICKUP_API_BASE = "https://api.clickup.com/api/v2"

CLICKUP_DEFAULT_LIST_ID = os.environ.get("CLICKUP_LIST_ID")

CLICKUP_TEST_CASE_TYPE_ID = os.environ.get("CLICKUP_TEST_CASE_TYPE_ID")

CLICKUP_SPACES = {
    "Herald": os.environ.get("CLICKUP_HERALD_SPACE_ID"),
    "Kupyo": os.environ.get("CLICKUP_KUPYO_SPACE_ID")
}

if not CLICKUP_API_KEY:
    print("⚠️ ADVERTENCIA: No se encontró CLICKUP_API_KEY en el archivo .env")