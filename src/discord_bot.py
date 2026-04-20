# src/discord_bot.py
import os
import asyncio
import discord
import random
import pytz
import requests
import datetime as dt
from discord.ext import commands, tasks
from discord.ui import Select, View
from pymongo import MongoClient
from dotenv import load_dotenv

# Importaciones de QA Autopilot
from core import clickup as C
from core import llm as L
from core import gherkin as G
from core.clickup import find_test_case_type_id 
from keep_alive import keep_alive  # Asegúrate de que keep_alive.py esté en la misma carpeta o accesible

load_dotenv()

# --- CONFIGURACIÓN DE TOKENS Y ENV ---
TOKEN = os.getenv('DISCORD_TOKEN')
MONGO_URI = os.getenv("MONGO_URI")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
GAS_WEB_APP_URL = os.getenv("GAS_WEB_APP_URL")

# Zona Horaria para la Ruleta
ARG_TZ = pytz.timezone('America/Argentina/Buenos_Aires')

# --- DATOS DE INTEGRANTES (RULETA) ---
INTEGRANTES_DATA = {
    "Juan Carlos Urquiza": "1460706682274451467",
    "Catriel Caruso": "1311265389723783179",
    "Angel Mendez": "1362026774988591299",
    "Sol Gosso": "1184514902963015710",
    "Luis Márquez": "1302037681227825215",
    "Matias Camiletti": "1043717500128481310",
    "Christian Ferrer": "1433452588183064658"
}
INTEGRANTES = list(INTEGRANTES_DATA.keys())

# --- CONFIGURACIÓN BASE DE DATOS ---
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["kupyo_bot"] 
history_collection = db["historial_dailys"] 
logs_collection = db["logs_ejecucion"] 

# --- INICIALIZACIÓN DEL BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ==========================================
# LÓGICA DE APOYO (RULETA)
# ==========================================

def get_now_arg():
    return dt.datetime.now(ARG_TZ)

def get_db_history():
    doc = history_collection.find_one({"_id": "estado_ruleta"})
    if not doc:
        doc = {"_id": "estado_ruleta", "this_week": [], "last_week": [], "week_num": -1}
        history_collection.insert_one(doc)
    return doc

def save_db_history(history_data):
    history_collection.update_one({"_id": "estado_ruleta"}, {"$set": history_data}, upsert=True)

def guardar_log(evento, detalles):
    ahora = get_now_arg()
    log_doc = {
        "fecha": ahora,
        "fecha_str": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "evento": evento,
        "detalles": detalles
    }
    logs_collection.insert_one(log_doc)

def get_mention(nombre):
    user_id = INTEGRANTES_DATA.get(nombre)
    return f"<@{user_id}>" if user_id else nombre

def get_calendar_availability():
    if not GAS_WEB_APP_URL:
        return None, {}, []
    try:
        response = requests.get(GAS_WEB_APP_URL, timeout=10)
        data = response.json()
        return data.get("motivo_cancelacion"), data.get("ausentes", {}), data.get("cumpleañeros", [])
    except Exception as e:
        print(f"🔥 Error Google Calendar: {e}")
        return None, {}, []

# ==========================================
# COMPONENTES DE INTERFAZ (RULETA)
# ==========================================

class SelectorNotas(discord.ui.Select):
    def __init__(self):
        opciones = [discord.SelectOption(label=nombre) for nombre in INTEGRANTES]
        super().__init__(
            placeholder="¿Alguien más tomó las notas hoy?",
            min_values=1, max_values=1, options=opciones,
            custom_id="selector_notas_v1" 
        )

    async def callback(self, interaction: discord.Interaction):
        self.disabled = True
        await interaction.response.edit_message(view=self.view)
        try:
            embed = interaction.message.embeds[0]
            principal_asignado = "Desconocido"
            for field in embed.fields:
                if "Principal" in field.name:
                    u_id = field.value.replace("<@", "").replace(">", "").replace("!", "")
                    for n, uid in INTEGRANTES_DATA.items():
                        if uid == u_id: principal_asignado = n; break
            
            anotador_real = self.values[0]
            hist = get_db_history()
            
            if principal_asignado in hist["this_week"]: hist["this_week"].remove(principal_asignado)
            if anotador_real not in hist["this_week"]: hist["this_week"].append(anotador_real)
            
            save_db_history(hist) 
            guardar_log("Cambio Manual de Notas", f"De {principal_asignado} a {anotador_real}")
            await interaction.followup.send(f"✅ Notas registradas a nombre de **{anotador_real}**.", ephemeral=True)
        except Exception as e:
            print(f"🔥 Error en cambio de notas: {e}")

class VistaRuleta(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) 
        self.add_item(SelectorNotas())

# ==========================================
# LÓGICA CENTRAL DE LA RULETA
# ==========================================

async def ejecutar_ruleta(canal):
    motivo, ausentes_dict, cumples = get_calendar_availability()
    history = get_db_history()
    today = get_now_arg()
    current_week = today.isocalendar()[1]
    
    embed = discord.Embed(color=0x3498DB)
    embed.set_footer(text=f"Semana {current_week} • {today.strftime('%d/%m/%Y')}")
    
    if motivo:
        es_feriado = "feriado" in motivo.lower() or "argentina" in motivo.lower()
        embed.title = "🏖️ ¡Día de Relax!" if es_feriado else "🔇 Modo Concentración"
        embed.color = 0x2ECC71 if es_feriado else 0x95A5A6
        saludo = "¡Disfruten muchísimo del descanso y recarguen pilas! 👋☀️" if es_feriado else "¡Día libre de reuniones! Aprovechen para meterle a fondo al código/tasks 👨‍💻🚀"
        embed.description = f"Hoy no corremos la ruleta porque tenemos: **{motivo}**.\n\n{saludo}"
        await canal.send(embed=embed)
        guardar_log("Ruleta Cancelada", motivo)
        return

    if history["week_num"] != current_week:
        history["last_week"], history["this_week"], history["week_num"] = history["this_week"], [], current_week

    candidatos = [m for m in INTEGRANTES if m not in history["this_week"] and m not in ausentes_dict]

    if not candidatos:
        embed.title = "⚠️ Sin candidatos"
        embed.description = "Parece que hoy no hay nadie disponible para el sorteo."
        await canal.send(embed=embed)
    else:
        prioridad = [m for m in candidatos if m not in history["last_week"]]
        principal = random.choice(prioridad) if prioridad else random.choice(candidatos)
        posibles_suplentes = [m for m in INTEGRANTES if m != principal and m not in ausentes_dict]
        suplente = random.choice(posibles_suplentes) if posibles_suplentes else "N/A"

        history["this_week"].append(principal)
        save_db_history(history)

        mencion_p = get_mention(principal)
        embed.title = "🎲 Ruleta de la Daily"
        embed.description = "¡El destino ha hablado! Estos son los responsables de hoy:"
        embed.add_field(name="📝 Principal", value=mencion_p, inline=True)
        embed.add_field(name="🛡️ Suplente", value=get_mention(suplente), inline=True)
        
        if ausentes_dict:
            txt = "\n".join([f"• **{p}**: {m}" for p, m in ausentes_dict.items()])
            embed.add_field(name="📋 Quiénes no están hoy", value=txt, inline=False)
        
        if cumples:
            txt = "\n".join([f"✨ ¡Feliz nivel nuevo {get_mention(c)}! 🎂🚀" for c in cumples])
            embed.add_field(name="🌟 ¡Hoy celebramos!", value=txt, inline=False)

        guardar_log("Sorteo Realizado", f"P: {principal} | S: {suplente}")
        await canal.send(content=f"🔔 ¡Atención {mencion_p}! El escenario es tuyo.", embed=embed, view=VistaRuleta())

# ==========================================
# TAREAS PROGRAMADAS Y EVENTOS
# ==========================================

@tasks.loop(time=dt.time(hour=17, minute=30, tzinfo=dt.timezone.utc))
async def tarea_diaria_ruleta():
    ahora = get_now_arg()
    if ahora.weekday() <= 4: # Lunes a Viernes
        canal = bot.get_channel(int(DISCORD_CHANNEL_ID))
        if canal: await ejecutar_ruleta(canal)

@bot.event
async def on_ready():
    print(f'🚀 Bot Unificado Listo: {bot.user}')
    # Registrar la vista para que los botones funcionen tras reiniciar
    bot.add_view(VistaRuleta()) 
    if not tarea_diaria_ruleta.is_running():
        tarea_diaria_ruleta.start()

# ==========================================
# COMANDOS (QA AUTOPILOT + RULETA)
# ==========================================

@bot.command(name="ruleta")
async def cmd_ruleta(ctx):
    """Comando manual para forzar la ruleta"""
    await ejecutar_ruleta(ctx.channel)

# --- CLASES Y COMANDOS DE QA AUTOPILOT (Tu código original) ---

class DestinationSelect(Select):
    def __init__(self, options, task_id, task_data, ctx):
        discord_options = [
            discord.SelectOption(label=opt["label"], value=opt["value"], description=opt["description"]) 
            for opt in options[:25]
        ]
        super().__init__(placeholder="📂 Selecciona dónde guardar los tests...", min_values=1, max_values=1, options=discord_options)
        self.task_id = task_id
        self.task_data = task_data
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content=f"✅ Destino: **{self.values[0]}**. \n🧠 La IA está pensando...", view=None)
        await self.generate_and_create(self.values[0])

    async def generate_and_create(self, list_id):
        try:
            is_backend = "[be]" in self.task_data["summary"].lower()
            sys_prompt = L.SYS_MSG_GENERATE_API_TESTS if is_backend else L.SYS_MSG_GENERATE_SCENARIOS

            scenarios, _ = await asyncio.to_thread(
                L.llm_generate_scenarios,
                issue_key=self.task_id,
                summary=self.task_data["summary"],
                full_context=self.task_data["full_context"],
                system_prompt=sys_prompt,
                images=self.task_data.get("images"),
                max_tests=50
            )

            if not scenarios:
                await self.ctx.send("⚠️ La IA no generó nada.")
                return

            progress_msg = await self.ctx.send(f"✍️ Escribiendo **{len(scenarios)}** Test Cases en ClickUp...")
            created_links = []
            
            def create_single_test(idx, sc):
                tc_id = f"TC{idx:02d}"
                formatted_title = f"{tc_id} | {self.task_id} | {sc['title']}"
                gherkin = G.build_feature_single(self.task_data["summary"], self.task_id, sc)
                return C.create_test_task(self.task_id, formatted_title, gherkin, list_id)

            for i, sc in enumerate(scenarios, 1):
                res = await asyncio.to_thread(create_single_test, i, sc)
                url = res.get("url")
                tc_id = f"TC{i:02d}"
                created_links.append(f"• [`{tc_id}`]({url}) {sc['title']}")

            story_link = f"https://app.clickup.com/t/{self.task_id}"
            header = f"🎉 **¡Proceso Finalizado!**\n📜 Historia: [**{self.task_data['summary']}**]({story_link})\n✅ Total Tests: **{len(created_links)}**\n\n👇 *Lista de casos:*:"
            await progress_msg.edit(content=header)

            chunk_size = 1900 
            current_chunk = ""
            for link in created_links:
                if len(current_chunk) + len(link) + 2 > chunk_size:
                    await self.ctx.send(current_chunk)
                    current_chunk = ""
                current_chunk += link + "\n"
            
            if current_chunk: await self.ctx.send(current_chunk)

        except Exception as e:
            await self.ctx.send(f"🔥 Error crítico: {str(e)}")

class DestinationView(View):
    def __init__(self, options, task_id, task_data, ctx):
        super().__init__()
        self.add_item(DestinationSelect(options, task_id, task_data, ctx))

@bot.command(name="clickup")
async def cmd_clickup(ctx, task_id: str):
    msg = await ctx.send(f"🕵️ Buscando tarea `{task_id}`...")
    try:
        task_data = await asyncio.to_thread(C.get_task, task_id)
        if not task_data.get("ok"):
            await msg.edit(content=f"❌ Error: {task_data.get('error')}")
            return

        available_lists = await asyncio.to_thread(C.get_testing_lists)
        if not available_lists:
            await msg.edit(content="⚠️ No encontré carpetas 'Testing Repository'.")
            return

        view = DestinationView(available_lists, task_id, task_data, ctx)
        await msg.edit(content=f"📂 Tarea: **{task_data['summary']}**\n👇 Destino:", view=view)
    except Exception as e:
        await msg.edit(content=f"🔥 Error: {str(e)}")

# ==========================================
# EJECUCIÓN
# ==========================================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ Falta TOKEN en el .env")
    else:
        keep_alive() # Inicia el servidor Flask para que el bot no se duerma
        bot.run(TOKEN)