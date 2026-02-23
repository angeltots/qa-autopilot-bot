# tests/test_clickup.py
import pytest
from unittest.mock import patch
from core import clickup

@patch('core.clickup.requests.request')
def test_get_team_id(mock_request):
    """Prueba que el bot pueda leer el ID del equipo de ClickUp correctamente"""
    mock_request.return_value.status_code = 200
    mock_request.return_value.json.return_value = {
        "teams": [{"id": "123456", "name": "Mi Equipo QA"}]
    }
    mock_request.return_value.text = "ok"
    
    team_id = clickup.get_team_id()
    assert team_id == "123456"

@patch('core.clickup.requests.request')
def test_create_test_task_payload(mock_request):
    """Prueba que se envíe el custom_task_type_id correcto al crear la tarea"""
    mock_request.return_value.status_code = 200
    mock_request.return_value.json.return_value = {"id": "abc987"}
    mock_request.return_value.text = "ok"
    
    clickup._CACHED_TEST_TYPE_ID = 1002
    
    clickup.create_test_task("parent_123", "Mi Test", "Given...", "list_456")
    
    llamadas = mock_request.call_args_list
    
    args_creacion, kwargs_creacion = llamadas[0]
    
    enviado = kwargs_creacion.get("json")
    
    assert enviado is not None, "El JSON no debería estar vacío"
    assert enviado["name"] == "Mi Test"
    assert enviado["custom_task_type_id"] == 1002