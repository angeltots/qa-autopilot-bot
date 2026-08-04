"""
Extract test cases from documentation sources using Google Gemini.

Supports three documentation sources:
  - PDF file (default: documentacion_oficial.pdf)
  - ClickUp Task (screenshots + description)
  - ClickUp Doc (rich-text pages)

Auth priority:
  1. GOOGLE_API_KEY  -- simple API key via Google AI Studio (cheapest for dev/low volume)
  2. GOOGLE_CLOUD_PROJECT_ID + GOOGLE_CLOUD_REGION -- Vertex AI (enterprise/production)
"""
import argparse
import json
import os
import sys
import logging

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("docs_extractor")

SYSTEM_PROMPT = (
    "You are a Senior QA Analyst.\n"
    "Read the documentation and extract test cases to validate the business rules described.\n"
    "RULES:\n"
    "1. Write in ENGLISH.\n"
    "2. Titles MUST start with 'Validate that'.\n"
    '3. Return ONLY a JSON object: {"tests_from_docs": [{"title": "...", "steps": "..."}]}'
)


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


def _parse_response(response) -> list:
    """Parse Gemini response text into a list of test dicts."""
    text = response.text
    if "```" in text:
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```"))
    data = json.loads(text.strip())
    return data.get("tests_from_docs", [])


def _gen_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        temperature=0.2,
    )


def extract_from_pdf(client, pdf_path: str, model: str) -> list:
    log.info(f"Loading {pdf_path}...")

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

    log.info("Extracting business rules from PDF via Gemini...")
    response = client.models.generate_content(
        model=model,
        contents=[pdf_part, "Extract all test cases from this document."],
        config=_gen_config(),
    )

    return _parse_response(response)


def extract_from_clickup_task(client, task_id: str, model: str) -> list:
    from core.clickup import get_task

    log.info(f"Fetching ClickUp task {task_id}...")
    task = get_task(task_id)
    if not task.get("ok"):
        log.error(f"Could not fetch task: {task.get('error')}")
        return []

    contents = []

    for img in task.get("images", []):
        contents.append(
            types.Part.from_bytes(data=img["data"], mime_type=img["mime_type"])
        )

    contents.append(
        task["full_context"] + "\n\nExtract all test cases from this documentation."
    )

    log.info("Extracting business rules from ClickUp task via Gemini...")
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=_gen_config(),
    )

    return _parse_response(response)


def extract_from_clickup_doc(client, doc_id: str, model: str) -> list:
    from core.clickup import get_doc_content

    log.info(f"Fetching ClickUp Doc {doc_id}...")
    content = get_doc_content(doc_id)
    if not content:
        log.error("Could not fetch doc content.")
        return []

    log.info("Extracting business rules from ClickUp Doc via Gemini...")
    response = client.models.generate_content(
        model=model,
        contents=[content + "\n\nExtract all test cases from this documentation."],
        config=_gen_config(),
    )

    return _parse_response(response)


def main():
    parser = argparse.ArgumentParser(description="Extract test cases from documentation")
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--pdf", default="documentacion_oficial.pdf", metavar="PATH",
        help="Path to PDF file (default: documentacion_oficial.pdf)"
    )
    source.add_argument(
        "--clickup-task", metavar="TASK_ID",
        help="ClickUp task ID to use as documentation source"
    )
    source.add_argument(
        "--clickup-doc", metavar="DOC_ID",
        help="ClickUp Doc ID (from URL: app.clickup.com/.../v/dc/DOC_ID/...)"
    )
    args = parser.parse_args()

    client = _init_client()
    if not client:
        log.error("No AI credentials found. Set GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT_ID in .env")
        return

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    try:
        if args.clickup_doc:
            log.info(f"Source: ClickUp Doc {args.clickup_doc}")
            tests = extract_from_clickup_doc(client, args.clickup_doc, model)
        elif args.clickup_task:
            log.info(f"Source: ClickUp task {args.clickup_task}")
            tests = extract_from_clickup_task(client, args.clickup_task, model)
        else:
            pdf_path = args.pdf
            if not os.path.exists(pdf_path):
                log.error(f"PDF not found: '{pdf_path}'")
                return
            log.info(f"Source: PDF {pdf_path}")
            tests = extract_from_pdf(client, pdf_path, model)

        output = {"tests_from_docs": tests}
        with open("tests_from_docs.json", "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        log.info(f"{len(tests)} test cases extracted -> tests_from_docs.json")

    except Exception as e:
        log.error(f"Error: {e}")


if __name__ == "__main__":
    main()
