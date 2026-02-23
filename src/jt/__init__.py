# src/jt/__init__.py

# --- Imports ---
import logging
import os
import time
import uuid
from typing import Any, Dict, List

# Core layer
from core import adf as A
from core import dedupe as D
from core import gherkin as G
from core import jira as J
from core import clickup as C  # <--- NUEVO IMPORT
from core import llm as L
from core.config import DEFAULT_PROJECT_KEY, RELATES_LINK_TYPE, CLICKUP_DEFAULT_LIST_ID

log = logging.getLogger(__name__)

# --- Configuration Constants ---
MAX_CONTEXT_CHARS = int(os.getenv("LLM_MAX_CONTEXT_CHARS", "16000"))
MAX_COMMENTS = int(os.getenv("LLM_MAX_COMMENTS", "10"))
MAX_COMMENT_CHARS = int(os.getenv("LLM_MAX_COMMENT_CHARS", "600"))

# --- Helper for formatting comments (SOLO PARA JIRA) ---
def format_and_filter_comments(comments_data: list) -> str:
    if not comments_data:
        return "No additional comments."
    formatted_comments: List[str] = []
    noise_filter = ("listo", "hecho", "done", "ok", "gracias", "de acuerdo")
    for comment in comments_data[:MAX_COMMENTS]:
        body_raw = comment.get("body", {})
        body_text = A.adf_to_text(body_raw).strip() if isinstance(body_raw, dict) else str(body_raw).strip()
        if not body_text or len(body_text.split()) < 3 or body_text.lower() in noise_filter:
            continue
        if len(body_text) > MAX_COMMENT_CHARS:
            body_text = body_text[:MAX_COMMENT_CHARS] + " [...]"
        author = comment.get("author", {}).get("displayName", "User")
        formatted_comments.append(f"- Comment from {author}: {body_text}")
    return "\n".join(formatted_comments) if formatted_comments else "No relevant comments found."

# --- Helper interno para crear issues en Jira ---
def _create_and_process_jira_test_case(**kwargs) -> Dict[str, Any]:
    created_issue = J.create_test_issue(
        project_key=kwargs['project_key'], summary=kwargs['summary'],
        description_text=kwargs['description'], gherkin=kwargs['gherkin_text'], labels=kwargs['labels']
    )
    new_key = created_issue["key"]
    try:
        J.link_issues(new_key, kwargs['source_issue_key'], link_type=kwargs['link_type'])
    except Exception:
        J.link_issues(new_key, kwargs['source_issue_key'], link_type=RELATES_LINK_TYPE)
    if kwargs['attach_feature']:
        try: J.attach_feature(new_key, kwargs['gherkin_text'], filename=kwargs['filename'])
        except Exception as e: logging.error(f"Failed to attach feature to {new_key}: {e}")
    if kwargs['fill_xray']:
        try: J.xray_import_feature(kwargs['gherkin_text'], project_key=kwargs['project_key'], test_key=new_key)
        except Exception as e: logging.error(f"Failed to import to Xray for {new_key}: {e}")
    return {"test_key": new_key, "summary": kwargs['summary'], "preview": kwargs['gherkin_text'][:300]}


# --- Tool Registration ---
def register_tools(mcp: Any):

    @mcp.tool()
    def diag_env() -> Dict[str, Any]:
        """Diagnóstico de conexiones (Jira y ClickUp)"""
        return {
            "JIRA_BASE": J.JIRA_BASE,
            "CLICKUP_API_BASE": C.CLICKUP_API_BASE,
            "GOOGLE_CLOUD_PROJECT_ID": L.PROJECT_ID,
            "status": "ok"
        }

    # ==========================================
    # HERRAMIENTA 1: JIRA (Tu lógica original)
    # ==========================================
    @mcp.tool()
    def jira_generate_tests(
        issue_key: str,
        target_project_key: str = DEFAULT_PROJECT_KEY,
        max_tests: int = 20,
        delete_obsolete: bool = False
    ) -> Dict[str, Any]:
        """Genera tests Gherkin para un ticket de JIRA."""
        rid = uuid.uuid4().hex[:8]
        log.info(f"[{rid}] Iniciando JIRA flow para {issue_key}…")

        src = J.get_issue(issue_key)
        if not src.get("ok"): return {"ok": False, "error": "Could not read source issue."}

        # 1. Preparar Contexto (Complejo por ADF)
        summary_src, desc = src["summary"], src["description"]
        comments_data = J.jira_request(f"/rest/api/3/issue/{issue_key}/comment").get("comments", [])
        relevant_comments = format_and_filter_comments(comments_data)
        full_context = f"STORY:\n{desc}\n\nCOMMENTS:\n{relevant_comments}"
        
        # 2. Generar con IA
        system_prompt = L.SYS_MSG_GENERATE_SCENARIOS # Simplificado para el ejemplo
        if "[be]" in summary_src.lower(): system_prompt = L.SYS_MSG_GENERATE_API_TESTS
        
        ideal_scenarios, _ = L.llm_generate_scenarios(issue_key, summary_src, full_context, max_tests, system_prompt)
        if not ideal_scenarios: return {"ok": False, "error": "LLM failed"}

        # 3. Sincronización (Update/Create/Obsolete)
        existing_tests = J.get_existing_tests_with_details(issue_key, target_project_key)
        sync_plan = L.llm_compare_and_sync(issue_key, summary_src, existing_tests, ideal_scenarios)

        report = {"created": [], "updated": [], "deleted": []}

        # Ejecutar Updates
        for item in sync_plan.get("to_update", []):
            J.update_test_issue(item['key'], item['summary'], item['steps'])
            report["updated"].append(item['key'])

        # Ejecutar Creates
        cur_index = J.next_tc_index(issue_key, target_project_key)
        for item in sync_plan.get("to_create", []):
            tc_tag = f"TC{cur_index:02d}"
            feature_text = G.build_feature_single(summary=summary_src, issue_key=issue_key, sc=item)
            res = _create_and_process_jira_test_case(
                project_key=target_project_key, summary=f"{issue_key} | {tc_tag} | {item['title']}",
                gherkin_text=feature_text, source_issue_key=issue_key, 
                description="Auto-generated", labels=["mcp", "auto-generated"], 
                link_type="Tests", attach_feature=True, fill_xray=False, filename=f"{issue_key}-{tc_tag}.feature"
            )
            report["created"].append(res["test_key"])
            cur_index += 1
            
        return {"ok": True, "report": report}

    # ==========================================
    # HERRAMIENTA 2: CLICKUP (La nueva lógica limpia)
    # ==========================================
    @mcp.tool()
    def clickup_generate_tests(
        task_id: str,
        list_id: str = CLICKUP_DEFAULT_LIST_ID,
        max_tests: int = 10
    ) -> Dict[str, Any]:
        """Genera tests Gherkin para una tarea de CLICKUP."""
        rid = uuid.uuid4().hex[:8]
        log.info(f"[{rid}] Iniciando CLICKUP flow para {task_id}…")
        
        # 1. Obtener Tarea (ClickUp nos da el texto limpio, fácil)
        task_data = C.get_task(task_id)
        if not task_data.get("ok"): return {"ok": False, "error": task_data.get("error")}
        
        # 2. Generar con IA (Reutilizamos el cerebro LLM)
        is_backend = "[be]" in task_data["summary"].lower()
        sys_prompt = L.SYS_MSG_GENERATE_API_TESTS if is_backend else L.SYS_MSG_GENERATE_SCENARIOS
        
        ideal_scenarios, _ = L.llm_generate_scenarios(
            issue_key=task_id, 
            summary=task_data["summary"], 
            full_context=task_data["full_context"], 
            max_tests=max_tests, 
            system_prompt=sys_prompt
        )

        # 3. Crear en ClickUp (Sin lógica compleja de sync por ahora, directo al grano)
        created = []
        for sc in ideal_scenarios:
            gherkin = G.build_feature_single(task_data["summary"], task_id, sc)
            res = C.create_test_task(task_id, f"[TEST] {sc['title']}", gherkin, list_id)
            created.append(res["key"])

        return {"ok": True, "created_tasks": created}