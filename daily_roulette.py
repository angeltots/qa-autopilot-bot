import os
import random
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Configuración desde Secretos de GitHub / Variables de Entorno
MONGO_URI = os.getenv('MONGO_URI') 
DB_NAME = "daily_bot_db"
COLLECTION_NAME = "history"
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN') # Usado por GitHub Actions

TEAMS = {
    "Kupyo": {
        "channel_id": os.getenv("DISCORD_CHANNEL_ID_KUPYO"),
        "members": ["Juan Carlos Urquiza", "Catriel Caruso", "Angel Mendez", "Sol Gosso", "Luis Márquez", "Matias Camiletti", "Christian Ferrer"]
    },
    "Herald": {
        "channel_id": os.getenv("DISCORD_CHANNEL_ID_HERALD"),
        "members": ["Juan Cruz Carvallo", "Francisco Dennehy", "Alejandro Moran", "Juan Carlos Urquiza", "Angel Mendez"]
    }
}

def get_mongo_client():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME][COLLECTION_NAME]

def run_roulette():
    collection = get_mongo_client()
    
    for team_name, config in TEAMS.items():
        channel_id = config["channel_id"]
        team = config["members"]
        
        if not channel_id:
            print(f"Saltando {team_name}, no hay channel_id configurado.")
            continue

        # 1. Obtener historial de Mongo (Usamos un tipo distinto por equipo)
        doc_type = f"daily_history_{team_name.lower()}"
        history_doc = collection.find_one({"type": doc_type})
        past_winners = history_doc.get("winners", []) if history_doc else []

        # 2. Filtrar disponibles
        available = [m for m in team if m not in past_winners]
        
        if not available:
            available = team
            past_winners = []

        # 3. Elegir ganador
        winner = random.choice(available)
        past_winners.append(winner)

        # 4. Guardar historial
        collection.update_one(
            {"type": doc_type},
            {"$set": {"winners": past_winners}},
            upsert=True
        )

        # 5. Enviar a Discord
        message = f"🎲 **Plan B Activado ({team_name})**\nEl encargado de la daily hoy es: **{winner}**"
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        requests.post(url, headers=headers, json={"content": message})
        print(f"Mensaje Plan B enviado a {team_name}")

if __name__ == "__main__":
    run_roulette()
