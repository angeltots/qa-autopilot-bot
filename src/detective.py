# get_real_types.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()
from core.config import CLICKUP_API_KEY
API_KEY = CLICKUP_API_KEY

def get_types():
    if not API_KEY:
        print("❌ Error: No hay API KEY en el .env")
        return

    headers = {"Authorization": API_KEY}
    
    print("qh Buscando Team ID...")
    resp_team = requests.get("https://api.clickup.com/api/v2/team", headers=headers)
    if resp_team.status_code != 200:
        print(f"Error Team: {resp_team.text}")
        return
        
    team_id = resp_team.json()["teams"][0]["id"]
    print(f"🏢 Team ID: {team_id}")

    print("📡 Descargando tipos de tarea configurados...")
    url = f"https://api.clickup.com/api/v2/team/{team_id}/custom_task_type"
    resp_types = requests.get(url, headers=headers)
    
    data = resp_types.json()
    
    print("\n 👇 --- LISTA OFICIAL DE TIPOS --- 👇")
    for t in data.get("custom_task_types", []):
        print(f"📛 Nombre: {t['name']}")
        print(f"🔑 ID REAL: {t['id']}") # <--- ESTE ES EL QUE NECESITAS
        print("-" * 30)

if __name__ == "__main__":
    get_types()