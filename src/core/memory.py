import json
import logging
import os
from datetime import date
from typing import Optional

log = logging.getLogger(__name__)

MEMORY_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "memory")
)

PROJECTS = {
    "herald": {
        "platform": "Greenway",
        "description": "Customer care and operations platform for Herald",
        "clickup_doc_id": "y5416-21954",
        "clickup_space_id": "90020038158",
    },
    "kupyo": {
        "platform": "Kupyo",
        "description": "TikTok-like social content platform for Kupyo",
        "clickup_doc_id": "y5416-21934",
        "clickup_space_id": "90140131483",
    },
}


def _memory_path(project: str) -> str:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    return os.path.join(MEMORY_DIR, f"{project}_context.json")


def load_memory(project: str) -> dict:
    path = _memory_path(project)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    meta = PROJECTS.get(project, {})
    return {
        "project": project,
        "platform": meta.get("platform", project),
        "description": meta.get("description", ""),
        "clickup_doc_id": meta.get("clickup_doc_id", ""),
        "clickup_space_id": meta.get("clickup_space_id", ""),
        "last_updated": str(date.today()),
        "modules_covered": [],
        "coverage": {},
        "business_rules": [],
        "ui_patterns": [],
        "pending_undocumented": [],
        "test_history": [],
    }


def save_memory(project: str, data: dict) -> None:
    data["last_updated"] = str(date.today())
    path = _memory_path(project)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info(f"Memory saved: {path}")


def memory_as_context(project: str) -> str:
    """Returns a formatted string to inject into LLM system prompts."""
    mem = load_memory(project)
    has_data = any([
        mem.get("modules_covered"),
        mem.get("business_rules"),
        mem.get("coverage"),
        mem.get("ui_patterns"),
    ])
    if not has_data:
        return ""

    covered = ", ".join(mem.get("modules_covered", [])) or "none yet"
    rules = "\n".join(f"  - {r}" for r in mem.get("business_rules", []))
    patterns = "\n".join(f"  - {p}" for p in mem.get("ui_patterns", []))

    lines = [
        f"PROJECT MEMORY -- {mem['project'].upper()} ({mem['platform']})",
        f"Last updated: {mem.get('last_updated')}",
        f"Modules already covered: {covered}",
    ]
    if rules:
        lines += ["Known business rules:", rules]
    if patterns:
        lines += ["UI patterns observed:", patterns]
    if mem.get("coverage"):
        lines += [f"Coverage detail: {json.dumps(mem['coverage'], ensure_ascii=False)}"]
    if mem.get("pending_undocumented"):
        lines += [f"Pending undocumented features: {json.dumps(mem['pending_undocumented'], ensure_ascii=False)}"]

    return "\n".join(lines)


def _llm_update(current_memory: dict, module: str, new_tests: list) -> Optional[dict]:
    """Calls Google Gemini to intelligently update project memory.

    Uses Google AI Studio (API key) for cost-effectiveness with gemini-flash models.
    Falls back to Vertex AI if API key is not available.
    """
    prompt_instruction = f"""You are a QA Knowledge Manager. Update the project memory JSON based on new test cases just created.

CURRENT MEMORY:
{json.dumps(current_memory, indent=2, ensure_ascii=False)}

MODULE JUST TESTED: {module}

NEW TEST CASES CREATED ({len(new_tests)} total):
{json.dumps(new_tests, indent=2, ensure_ascii=False)}

RULES:
1. Add "{module}" to modules_covered if not already there.
2. Update coverage["{module}"] with: total count, and count per status (Ready_for_Automation, Missing_in_UI, Undocumented_Feature).
3. Extract NEW business rules from test titles/steps -- short factual sentences (e.g. "Search returns max 50 results"). Do not duplicate existing ones.
4. Extract NEW UI patterns observed (buttons, filters, tables, modals found). Do not duplicate.
5. Move any Undocumented_Feature tests into pending_undocumented (title only, if not already there).
6. Append a summary entry to test_history: {{"date": "{date.today()}", "module": "{module}", "total": N, "statuses": {{...}}}}.
7. Keep ALL existing data -- only add or update, never remove.
8. Return ONLY pure JSON with the exact same structure as CURRENT MEMORY."""

    google_key = os.getenv("GOOGLE_API_KEY", "")
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "")

    # Gemini is the primary LLM for this project (cost-effective with flash models)
    if google_key or project_id:
        try:
            from google import genai
            from google.genai import types

            if google_key:
                client = genai.Client(api_key=google_key)
            else:
                location = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
                client = genai.Client(vertexai=True, project=project_id, location=location)

            model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            response = client.models.generate_content(
                model=model,
                contents=prompt_instruction,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            log.error(f"Gemini memory update failed: {e}")

    log.warning("No LLM available for memory update -- skipping intelligent update.")
    return None


def update_memory(project: str, module: str, new_tests: list) -> None:
    """Updates project memory with insights from a pipeline run."""
    if not new_tests:
        log.info("No tests to learn from -- memory unchanged.")
        return

    log.info(f"Updating memory for {project}/{module} ({len(new_tests)} tests)...")
    current = load_memory(project)
    updated = _llm_update(current, module, new_tests)

    if updated:
        save_memory(project, updated)
        log.info(f"Memory updated for {project}.")
    else:
        _fallback_update(project, module, new_tests, current)


def _fallback_update(project: str, module: str, new_tests: list, current: dict) -> None:
    """Simple deterministic update when no LLM is available."""
    if module not in current["modules_covered"]:
        current["modules_covered"].append(module)

    statuses: dict = {}
    for t in new_tests:
        s = t.get("status", "unknown")
        statuses[s] = statuses.get(s, 0) + 1

    current["coverage"][module] = {"total": len(new_tests), "statuses": statuses}

    undocumented = [
        t["title"] for t in new_tests if t.get("status") == "Undocumented_Feature"
    ]
    existing_pending = set(current.get("pending_undocumented", []))
    current["pending_undocumented"] = list(existing_pending | set(undocumented))

    current.setdefault("test_history", []).append({
        "date": str(date.today()),
        "module": module,
        "total": len(new_tests),
        "statuses": statuses,
    })

    save_memory(project, current)
    log.info(f"Memory updated (fallback mode) for {project}.")
