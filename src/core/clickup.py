# src/core/clickup.py
import time
import logging
import requests
from typing import Dict, List, Any, Optional
from .config import CLICKUP_API_KEY, CLICKUP_API_BASE, CLICKUP_SPACES, CLICKUP_TEST_CASE_TYPE_ID

log = logging.getLogger(__name__)

_CACHED_TEAM_ID = None
_CACHED_TEST_TYPE_ID = None

def _headers() -> dict:
    if not CLICKUP_API_KEY: raise ValueError("Falta CLICKUP_API_KEY")
    return {"Authorization": CLICKUP_API_KEY, "Content-Type": "application/json"}

def clickup_request(method: str, path: str, params: dict = None, body: dict = None) -> dict:
    url = f"{CLICKUP_API_BASE.rstrip('/')}{path}"
    for attempt in range(1, 4):
        try:
            resp = requests.request(method, url, headers=_headers(), params=params, json=body, timeout=30)
            if resp.status_code == 429:
                time.sleep(2)
                continue
            resp.raise_for_status()
            return resp.json() if resp.text else {}
        except Exception as e:
            log.warning(f"Error ClickUp: {e}")
            if attempt == 3: raise
            time.sleep(1)


def get_team_id() -> Optional[str]:
    global _CACHED_TEAM_ID
    if _CACHED_TEAM_ID: return _CACHED_TEAM_ID
    try:
        data = clickup_request("GET", "/team")
        teams = data.get("teams", [])
        if teams:
            _CACHED_TEAM_ID = teams[0]["id"]
            return _CACHED_TEAM_ID
    except Exception: pass
    return None

def find_test_case_type_id() -> Optional[int]:
    """Busca el ID de 'Test Case'. Prioriza variable de config."""
    global _CACHED_TEST_TYPE_ID
    
    if _CACHED_TEST_TYPE_ID: return _CACHED_TEST_TYPE_ID

    if CLICKUP_TEST_CASE_TYPE_ID:
        try:
            _CACHED_TEST_TYPE_ID = int(CLICKUP_TEST_CASE_TYPE_ID)
            return _CACHED_TEST_TYPE_ID
        except ValueError:
            pass 

    team_id = get_team_id()
    if not team_id: return None

    try:
        data = clickup_request("GET", f"/team/{team_id}/custom_task_type")
        types = data.get("custom_task_types", [])
        target_names = ["test case", "test", "prueba", "caso de prueba"]
        for t in types:
            if t.get("name", "").lower() in target_names:
                _CACHED_TEST_TYPE_ID = t.get("id")
                return _CACHED_TEST_TYPE_ID
    except Exception: pass
    
    return None


def get_folders_in_space(space_id: str) -> List[dict]:
    if not space_id: return []
    data = clickup_request("GET", f"/space/{space_id}/folder")
    return data.get("folders", [])

def get_lists_in_folder(folder_id: str) -> List[dict]:
    data = clickup_request("GET", f"/folder/{folder_id}/list")
    return data.get("lists", [])

def get_testing_lists() -> List[Dict[str, str]]:
    options = []
    for project_name, space_id in CLICKUP_SPACES.items():
        if not space_id: continue
        folders = get_folders_in_space(space_id)
        target_folder = None
        for f in folders:
            if "testing" in f["name"].lower() and "repository" in f["name"].lower():
                target_folder = f
                break
        if target_folder:
            lists = get_lists_in_folder(target_folder["id"])
            for l in lists:
                options.append({
                    "label": f"{project_name} - {l['name']}",
                    "value": l["id"],
                    "description": f"Carpeta: {target_folder['name']}"
                })
    return options

def get_task_images(task_id: str) -> List[Dict[str, Any]]:
    try:
        data = clickup_request("GET", f"/task/{task_id}")
        attachments = data.get("attachments", [])
        image_data = []
        for att in attachments:
            if att.get("type", "").startswith("image/"):
                url = att.get("url")
                img_resp = requests.get(url, headers={"Authorization": CLICKUP_API_KEY})
                if img_resp.status_code == 200:
                    image_data.append({"mime_type": att.get("type"), "data": img_resp.content, "name": att.get("name")})
        return image_data
    except Exception: return []

def get_task(task_id: str) -> dict:
    try:
        data = clickup_request("GET", f"/task/{task_id}")
        desc = data.get("description", "") or ""
        name = data.get("name", "")
        comments_data = clickup_request("GET", f"/task/{task_id}/comment")
        comments_list = [f"{c['user']['username']}: {c['comment_text']}" for c in comments_data.get("comments", [])]
        return {
            "ok": True, "key": data.get("id"), "summary": name, "description": desc,
            "full_context": f"TITLE: {name}\nDESCRIPTION:\n{desc}\nCOMMENTS:\n{chr(10).join(comments_list)}",
            "images": get_task_images(task_id)
        }
    except Exception as e: return {"ok": False, "error": str(e)}

def create_test_task(parent_task_id: str, summary: str, gherkin: str, list_id: str) -> dict:
    if not list_id: raise ValueError("Falta lista destino.")

    custom_type_id = find_test_case_type_id()

    body = {
        "name": summary,
        "description": f"```gherkin\n{gherkin}\n```",
        "tags": ["auto-generated", "mcp-test"],
    }

    if custom_type_id:
        body["custom_task_type_id"] = custom_type_id

    print(f"🛑 [DEBUG CLICKUP] Tipo ID: {custom_type_id} | Título: {summary}")

    data = clickup_request("POST", f"/list/{list_id}/task", body=body)
    new_task_id = data.get("id")
    task_url = f"https://app.clickup.com/t/{new_task_id}"
    
    try: clickup_request("POST", f"/task/{parent_task_id}/link/{new_task_id}")
    except: pass

    return {"ok": True, "key": new_task_id, "url": task_url}