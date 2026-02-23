# src/core/llm.py
import os
import json
import logging
from typing import List, Dict, Tuple, Any

from google import genai
from google.genai import types

log = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
LOCATION = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")

client = None
provider = "unknown"

try:
    if GOOGLE_API_KEY:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        provider = "google-ai-studio"
    elif PROJECT_ID:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
        provider = "vertex-ai"
    else:
        log.warning("No hay credenciales de IA configuradas en el .env")
except Exception as e:
    log.error(f"Faltan librerías o credenciales de IA: {e}")

SYS_MSG_GENERATE_SCENARIOS = (
    "You are a Senior QA Analyst focused on Acceptance Testing.\n"
    "INPUT ANALYSIS RULES:\n"
    "1. **FOCUS ON EXPECTED BEHAVIOR:** If the input is a Bug Report, IGNORE the 'Current Behavior' or 'Actual Result'. Do NOT write tests to reproduce the bug. Write tests to verify the **FIX** (the Expected Behavior).\n"
    "2. **VALIDATION ONLY:** Your goal is to ensure the requirement works as intended.\n"
    "\n"
    "FORMATTING RULES:\n"
    "1. **TITLES:** MUST start with the phrase **'Validate that'**. Example: 'Validate that the user is redirected to the app...'.\n"
    "2. **NO LABELS:** Do NOT use prefixes like 'Bug:', 'Happy Path:', 'Edge Case:', or 'Scenario:'. Just the action.\n"
    "3. **SCOPE:** Generate enough scenarios to cover the Expected Behavior fully (Positive flows and necessary validations).\n"
    "4. **OUTPUT:** Single JSON object: {\"scenarios\": [{\"title\": \"...\", \"steps\": \"...\"}]}"
)

SYS_MSG_GENERATE_API_TESTS = (
    "You are a Backend QA Expert.\n"
    "RULES:\n"
    "1. FOCUS: Validate the API contract, successful responses (200/201), and expected error handling (400/404) defined in requirements.\n"
    "2. TITLES: MUST start with **'Validate that'**.\n"
    "3. OUTPUT: Single JSON object: {\"scenarios\": [{\"title\": \"...\", \"steps\": \"...\"}]}"
)

def _clean_json_text(text: str) -> str:
    """Limpia bloques markdown ```json ... ```"""
    if "```" in text:
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        return "\n".join(lines)
    return text

def llm_generate_scenarios(
    issue_key: str,
    summary: str,
    full_context: str,
    max_tests: int = 50, 
    system_prompt: str = SYS_MSG_GENERATE_SCENARIOS,
    images: List[Dict] = None
) -> Tuple[List[Dict[str, str]], str]:
    
    if not client:
        return [], "Error: Cliente de IA no configurado."

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    try:
        user_prompt = (
            f"TASK: {issue_key}\n"
            f"SUMMARY: {summary}\n"
            f"CONTEXT:\n{full_context}\n\n"
            "INSTRUCTION: Create Gherkin Test Cases to VALIDATE the Expected Behavior. "
            "Ensure all titles start with 'Validate that'. Return JSON."
        )
        
        # Preparamos el contenido (Texto + Imágenes si hay)
        contents = [user_prompt]
        if images:
            for img in images:
                contents.append(
                    types.Part.from_bytes(data=img["data"], mime_type=img["mime_type"])
                )
        
        # Llamamos a Gemini (¡El mismo código para Vertex o AI Studio!)
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.2
            )
        )

        clean_text = _clean_json_text(response.text)
        data = json.loads(clean_text)
        scenarios = data.get("scenarios", [])
        
        final_scenarios = []
        for sc in scenarios[:max_tests]: 
            t = sc.get("title", "Untitled").strip()
            
            lower_t = t.lower()
            for prefix in ["bug:", "happy path:", "scenario:", "edge case:", "test case:"]:
                if lower_t.startswith(prefix):
                    t = t[len(prefix):].strip()
            
            if not t.lower().startswith("validate that"):
                if t.lower().startswith("verify"):
                    t = "Validate that" + t[6:]
                elif t.lower().startswith("ensure"):
                    t = "Validate that" + t[6:]
                else:
                    t = f"Validate that {t}"
            
            s = sc.get("steps", [])
            s_str = "\n".join(s) if isinstance(s, list) else str(s)
            
            if t and s_str:
                final_scenarios.append({"title": t, "steps": s_str})

        log.info(f"✅ IA generó {len(final_scenarios)} tests de validación via {provider}.")
        return final_scenarios, provider

    except Exception as e:
        log.error(f"Error LLM: {e}")
        return [], str(e)

def llm_compare_and_sync(issue_key: str, summary: str, existing_tests: list, new_scenarios: list) -> dict:
    """
    Compara los tests que ya existen con los que acaba de generar la IA
    para decidir qué crear, qué actualizar y qué marcar como obsoleto.
    """
    plan = {
        "to_create": [],
        "to_update": [],
        "obsolete": [],
        "unchanged": []
    }
    
    existing_map = {}
    for t in existing_tests:
        t_title = t.get("norm_title") or t.get("title") or t.get("summary") or ""
        
        if " | " in t_title:
            t_title = t_title.split(" | ", 1)[-1].strip()
            
        existing_map[t_title.strip().lower()] = t
        
    matched_keys = set()
    
    for sc in new_scenarios:
        sc_title = sc.get("title", "").strip()
        sc_steps = sc.get("steps", "").strip()
        
        search_title = sc_title
        if " | " in search_title:
            search_title = search_title.split(" | ", 1)[-1].strip()
            
        match = existing_map.get(search_title.lower())
        
        if match:
            matched_keys.add(match["key"])
            match_steps = (match.get("gherkin") or match.get("steps") or match.get("description") or "").strip()
            
            if match_steps != sc_steps:
                match_updated = match.copy()
                match_updated["steps"] = sc_steps
                plan["to_update"].append(match_updated)
            else:
                plan["unchanged"].append(match)
        else:
            plan["to_create"].append(sc)
            
    for t in existing_tests:
        if t["key"] not in matched_keys:
            plan["obsolete"].append(t)
            
    return plan