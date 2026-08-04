"""
Reconcile test cases from documentation (Source A) and UI exploration (Source B)
into a unified test list using Google Gemini.

Auth priority:
  1. GOOGLE_API_KEY  -- simple API key via Google AI Studio
  2. GOOGLE_CLOUD_PROJECT_ID + GOOGLE_CLOUD_REGION -- Vertex AI
"""
import json
import os
import logging

from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("reconciliation")

SYSTEM_PROMPT = """You are a Lead QA Automation Engineer. Reconcile two test case sources into one unified list.

CONTEXT:
- Source A (Documentation): Business rules for the ENTIRE system.
- Source B (UI Reality): Only what was observed on a specific screen.

RULES:
1. EXCLUDE tests from Source A that belong to other modules (Invoices, Backorders, Contracts, etc.).
   Focus ONLY on the module visible in Source B.
2. Test in BOTH sources -> "status": "Ready_for_Automation"
   - Title: Use formal title from Source A.
   - Steps: Convert Source B steps to STRICT GHERKIN (Given, When, Then, And). No numbered lists.
3. Test in A but NOT in B -> "status": "Missing_in_UI". Convert steps to Gherkin.
4. Test in B but NOT in A -> "status": "Undocumented_Feature". Convert steps to Gherkin.
5. Return ONLY a JSON object: {"final_tests": [{"title": "...", "steps": "...", "status": "..."}]}"""


def _init_client():
    """Initialize the Gemini client with API key (preferred) or Vertex AI."""
    api_key = os.getenv("GOOGLE_API_KEY")
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    location = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")

    if api_key:
        log.info("Using Google AI Studio (API key)")
        return genai.Client(api_key=api_key)
    elif project_id:
        log.info(f"Using Vertex AI (project: {project_id}, region: {location})")
        return genai.Client(vertexai=True, project=project_id, location=location)
    else:
        return None


def main():
    log.info("Starting intelligent reconciliation (Docs vs UI)...")

    try:
        with open("tests_from_docs.json", "r", encoding="utf-8") as f:
            docs_data = f.read()
        with open("tests_from_web.json", "r", encoding="utf-8") as f:
            web_data = f.read()
    except FileNotFoundError as e:
        log.error(f"Missing input file: {e}")
        return

    client = _init_client()
    if not client:
        log.error("No AI credentials found. Set GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT_ID in .env")
        return

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    user_prompt = f"SOURCE A (Documentation):\n{docs_data}\n\nSOURCE B (UI Screen):\n{web_data}"

    log.info(f"Gemini ({model}) is reconciling both sources...")

    try:
        response = client.models.generate_content(
            model=model,
            contents=[user_prompt],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        text = response.text
        if "```" in text:
            text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```"))

        parsed = json.loads(text.strip())
        with open("final_tests_to_create.json", "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)

        count = len(parsed.get("final_tests", []))
        statuses = {}
        for t in parsed.get("final_tests", []):
            s = t.get("status", "unknown")
            statuses[s] = statuses.get(s, 0) + 1

        log.info(f"Reconciliation complete! {count} tests -> final_tests_to_create.json")
        for status, n in statuses.items():
            log.info(f"   {status}: {n}")

    except Exception as e:
        log.error(f"Reconciliation error: {e}")


if __name__ == "__main__":
    main()
