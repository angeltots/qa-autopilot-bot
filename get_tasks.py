import requests
import os
import asyncio
from dotenv import load_dotenv

TOKEN = os.getenv('DISCORD_TOKEN')
FOLDER_ID = "90144557518"

headers = {"Authorization": TOKEN, "Content-Type": "application/json"}

def get_all_tasks_recursive(list_id):
    """Trae todas las tareas y subtareas sin importar la profundidad."""
    url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
    params = {
        "subtasks": "true", 
        "include_closed": "true",
        "page": 0
    }
    
    all_found = []
    while True:
        resp = requests.get(url, headers=headers, params=params).json()
        tasks = resp.get("tasks", [])
        if not tasks:
            break
        all_found.extend(tasks)
        if len(tasks) < 100:
            break
        params["page"] += 1
    
    return all_found

def run_deep_scan():
    lists_url = f"https://api.clickup.com/api/v2/folder/{FOLDER_ID}/list"
    lists = requests.get(lists_url, headers=headers).json().get("lists", [])
    
    print("# 🏁 REPORTE DEFINITIVO DE TEST CASES - KUPYO V2.1\n")
    
    for l in lists:
        print(f"## 📋 {l['name']}")
        tasks = get_all_tasks_recursive(l['id'])
        
        hierarchy = {}
        for t in tasks:
            parent_id = t.get('parent')
            if not parent_id:
                if t['id'] not in hierarchy: hierarchy[t['id']] = {'name': t['name'], 'subs': []}
            else:
                if parent_id not in hierarchy: hierarchy[parent_id] = {'name': 'Folder/Parent Task', 'subs': []}
                hierarchy[parent_id]['subs'].append(t['name'])
        
        for parent_id, data in hierarchy.items():
            if data['name'] != 'Folder/Parent Task':
                print(f"- [ ] **{data['name']}**")
            
            for sub in data['subs']:
                print(f"  - [ ] {sub}")
        
        print("\n" + "---" * 10 + "\n")

if __name__ == "__main__":
    run_deep_scan()