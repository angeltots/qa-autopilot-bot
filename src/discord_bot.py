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
from keep_alive import keep_alive  

load_dotenv()

# --- CONFIGURACIÓN DE TOKENS Y ENV ---
TOKEN = os.getenv('DISCORD_TOKEN')
MONGO_URI = os.getenv("MONGO_URI")
GAS_WEB_APP_URL = os.getenv("GAS_WEB_APP_URL")

# Zona Horaria para la Ruleta
ARG_TZ = pytz.timezone('America/Argentina/Buenos_Aires')

# --- CONFIGURACIÓN DE EQUIPOS Y CANALES ---
TEAMS = {
    "Kupyo": {
        "channel_id": os.getenv("DISCORD_CHANNEL_ID_KUPYO"),
        "report_channel_id": os.getenv("DISCORD_REPORT_CHANNEL_ID_KUPYO"),
        "db_key": "estado_ruleta_kupyo",
        "calendar_key": "daily_kupyo",
        "mensaje_cumple": "✨ **¡Feliz nivel nuevo {mencion}!** 🎂🚀 Todos en **Kupyo** deseamos que tengas un gran día y lo pases increíble.",
        "members": {
            "Juan Carlos Urquiza": "1460706682274451467",
            "Catriel Caruso": "1311265389723783179",
            "Angel Mendez": "1362026774988591299",
            "Sol Gosso": "1184514902963015710",
            "Luis Márquez": "1302037681227825215",
            "Matias Camiletti": "1043717500128481310",
            "Christian Ferrer": "1433452588183064658"
        }
    },
    "Herald": {
        "channel_id": os.getenv("DISCORD_CHANNEL_ID_HERALD"),
        "report_channel_id": os.getenv("DISCORD_REPORT_CHANNEL_ID_HERALD"),
        "db_key": "estado_ruleta_herald",
        "calendar_key": "daily_herald",
        "mensaje_cumple": "🎉 **¡Muy feliz cumple {mencion}!** 🥳🎈 Desde el equipo de **Herald** te mandamos un gran abrazo y los mejores deseos para tu día.",
        "members": {
            "Juan Cruz Carvallo": "1170912463852675213", 
            "Francisco Dennehy": "1194998607238140017", 
            "Alejandro Moran": "1341143520173494292",    
            "Juan Carlos Urquiza": "1460706682274451467",
            "Angel Mendez": "1362026774988591299"
        }
    }
}

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

def get_db_history(db_key):
    doc = history_collection.find_one({"_id": db_key})
    if not doc:
        doc = {"_id": db_key, "this_week": [], "last_week": [], "week_num": -1}
        history_collection.insert_one(doc)
    return doc

def save_db_history(db_key, history_data):
    history_collection.update_one({"_id": db_key}, {"$set": history_data}, upsert=True)

def guardar_log(evento, detalles):
    ahora = get_now_arg()
    log_doc = {
        "fecha": ahora,
        "fecha_str": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "evento": evento,
        "detalles": detalles
    }
    logs_collection.insert_one(log_doc)

def get_mention(nombre, team_members):
    user_id = team_members.get(nombre)
    return f"<@{user_id}>" if user_id else nombre

def get_calendar_availability():
    if not GAS_WEB_APP_URL:
        return {}
    try:
        response = requests.get(GAS_WEB_APP_URL, timeout=10)
        return response.json()
    except Exception as e:
        print(f"🔥 Error Google Calendar: {e}")
        return {}

# ==========================================
# COMPONENTES DE INTERFAZ (RULETA)
# ==========================================

class SelectorNotas(discord.ui.Select):
    def __init__(self, team_name):
        self.team_name = team_name
        integrantes = list(TEAMS[team_name]["members"].keys())
        opciones = [discord.SelectOption(label=nombre) for nombre in integrantes]
        super().__init__(
            placeholder="¿Alguien más tomó las notas hoy?",
            min_values=1, max_values=1, options=opciones,
            custom_id=f"selector_notas_{team_name}" 
        )

    async def callback(self, interaction: discord.Interaction):
        self.disabled = True
        await interaction.response.edit_message(view=self.view)
        try:
            embed = interaction.message.embeds[0]
            principal_asignado = "Desconocido"
            team_members = TEAMS[self.team_name]["members"]
            
            for field in embed.fields:
                if "Principal" in field.name:
                    u_id = field.value.replace("<@", "").replace(">", "").replace("!", "")
                    for n, uid in team_members.items():
                        if uid == u_id: principal_asignado = n; break
            
            anotador_real = self.values[0]
            db_key = TEAMS[self.team_name]["db_key"]
            hist = get_db_history(db_key)
            
            if principal_asignado in hist["this_week"]: hist["this_week"].remove(principal_asignado)
            if anotador_real not in hist["this_week"]: hist["this_week"].append(anotador_real)
            
            save_db_history(db_key, hist) 
            guardar_log(f"Cambio Manual ({self.team_name})", f"De {principal_asignado} a {anotador_real}")
            await interaction.followup.send(f"✅ Notas registradas a nombre de **{anotador_real}**.", ephemeral=True)
        except Exception as e:
            print(f"🔥 Error en cambio de notas: {e}")

class VistaRuleta(discord.ui.View):
    def __init__(self, team_name):
        super().__init__(timeout=None) 
        self.add_item(SelectorNotas(team_name))

# ==========================================
# LÓGICA CENTRAL DE LA RULETA
# ==========================================

async def ejecutar_ruleta_equipo(team_name):
    config = TEAMS[team_name]
    canal_equipo = bot.get_channel(int(config["channel_id"])) if config.get("channel_id") else None
    canal_reportes = bot.get_channel(int(config["report_channel_id"])) if config.get("report_channel_id") else None
    
    if not canal_equipo: return

    cal_data = get_calendar_availability()
    motivo_cancelacion = cal_data.get("motivo_cancelacion")
    free_meetings_day = cal_data.get("free_meetings_day", False)
    hay_daily = cal_data.get(config["calendar_key"], False)
    ausentes_dict = cal_data.get("ausentes", {})
    cumples = cal_data.get("cumpleañeros", [])
    
    today = get_now_arg()
    current_week = today.isocalendar()[1]
    
    if motivo_cancelacion and "feriado" in motivo_cancelacion.lower():
        embed = discord.Embed(title="🏖️ ¡Día de Relax!", color=0x2ECC71)
        embed.description = f"Hoy no corremos la ruleta en **{team_name}** porque tenemos: **{motivo_cancelacion}**.\n\n¡Disfruten muchísimo del descanso y recarguen pilas! 👋☀️"
        await canal_equipo.send(embed=embed)
        return

    if free_meetings_day or not hay_daily:
        if canal_reportes:
            embed = discord.Embed(title=f"🔇 Sin Daily por llamada hoy para {team_name}", color=0x95A5A6)
            razon = "es Free Meetings Day" if free_meetings_day else "no se agendó la reunión en el calendario"
            
            embed.description = (
                f"Hoy no tenemos reunión por llamada porque **{razon}**.\n\n"
                "📝 **Por favor, dejen su reporte diario por escrito respondiendo en este canal.**\n"
                "Comenten en qué status están sus tareas y si tienen algún blocker. 👇"
            )
            
            # 1. Obtenemos a todos los integrantes de este equipo
            integrantes = list(config["members"].keys())
            
            # 2. Filtramos SOLO a los que NO están en la lista de ausentes
            presentes = [m for m in integrantes if m not in ausentes_dict]
            
            # 3. Armamos las menciones solo para los presentes
            if presentes:
                menciones = " ".join([get_mention(m, config["members"]) for m in presentes])
                mensaje_ping = f"🔔 ¡Atención equipo! {menciones}"
            else:
                # Caso extremo: todos están de vacaciones/people day
                mensaje_ping = "🔔 ¡Atención equipo! (Aunque parece que hoy todos están descansando 🌴)"
            
            # Enviamos el mensaje con las menciones
            await canal_reportes.send(content=mensaje_ping, embed=embed)
            guardar_log(f"Sin Daily ({team_name})", razon)
        else:
            print(f"⚠️ {team_name} cancelado por {razon}, pero no hay canal de reportes configurado.")
        return

    history = get_db_history(config["db_key"])
    if history["week_num"] != current_week:
        history["last_week"], history["this_week"], history["week_num"] = history["this_week"], [], current_week

    integrantes = list(config["members"].keys())
    candidatos = [m for m in integrantes if m not in history["this_week"] and m not in ausentes_dict]

    embed = discord.Embed(color=0x3498DB)
    embed.set_footer(text=f"Semana {current_week} • {today.strftime('%d/%m/%Y')}")

    if not candidatos:
        embed.title = f"⚠️ Sin candidatos en {team_name}"
        embed.description = "Parece que hoy no hay nadie disponible para el sorteo."
        await canal_equipo.send(embed=embed)
    else:
        prioridad = [m for m in candidatos if m not in history["last_week"]]
        principal = random.choice(prioridad) if prioridad else random.choice(candidatos)
        posibles_suplentes = [m for m in integrantes if m != principal and m not in ausentes_dict]
        suplente = random.choice(posibles_suplentes) if posibles_suplentes else "N/A"

        history["this_week"].append(principal)
        save_db_history(config["db_key"], history)

        mencion_p = get_mention(principal, config["members"])
        embed.title = f"🎲 Ruleta de la Daily - {team_name}"
        embed.description = "¡El destino ha hablado! Estos son los responsables de hoy:"
        embed.add_field(name="📝 Principal", value=mencion_p, inline=True)
        embed.add_field(name="🛡️ Suplente", value=get_mention(suplente, config["members"]), inline=True)
        
        if ausentes_dict:
            txt = "\n".join([f"• **{p}**: {m}" for p, m in ausentes_dict.items() if p in integrantes])
            if txt: embed.add_field(name="📋 Quiénes no están hoy", value=txt, inline=False)
        
        if cumples:
            # Usamos la plantilla personalizada de cumpleaños
            txt = "\n".join([config["mensaje_cumple"].format(mencion=get_mention(c, config['members'])) for c in cumples if c in integrantes])
            if txt: embed.add_field(name="🌟 ¡Hoy celebramos!", value=txt, inline=False)

        await canal_equipo.send(content=f"🔔 ¡Atención {mencion_p}! El escenario es tuyo.", embed=embed, view=VistaRuleta(team_name))

# ==========================================
# TAREAS PROGRAMADAS
# ==========================================

# 10:30 AM ART = 13:30 UTC
HORA_HERALD = dt.time(hour=13, minute=30, tzinfo=dt.timezone.utc)
# 14:30 PM ART = 17:30 UTC
HORA_KUPYO = dt.time(hour=17, minute=30, tzinfo=dt.timezone.utc)
# Fin de semana (9:00 AM ART = 12:00 UTC)
HORA_CUMPLES_FINDE = dt.time(hour=12, minute=0, tzinfo=dt.timezone.utc)

@tasks.loop(time=HORA_HERALD)
async def tarea_herald():
    if get_now_arg().weekday() <= 4: await ejecutar_ruleta_equipo("Herald")

@tasks.loop(time=HORA_KUPYO)
async def tarea_kupyo():
    if get_now_arg().weekday() <= 4: await ejecutar_ruleta_equipo("Kupyo")

@tasks.loop(time=HORA_CUMPLES_FINDE)
async def tarea_cumples_fin_de_semana():
    if get_now_arg().weekday() >= 5:
        cal_data = get_calendar_availability()
        cumples = cal_data.get("cumpleañeros", [])
        if not cumples: return

        for team_name, config in TEAMS.items():
            canal_equipo = bot.get_channel(int(config["channel_id"]))
            if not canal_equipo: continue
            cumples_equipo = [c for c in cumples if c in config["members"]]
            
            if cumples_equipo:
                embed = discord.Embed(title="🌟 ¡Celebración de Fin de Semana! 🎂", color=0xF1C40F)
                # Usamos la plantilla personalizada también aquí
                txt = "\n".join([config["mensaje_cumple"].format(mencion=get_mention(c, config['members'])) for c in cumples_equipo])
                embed.description = txt
                await canal_equipo.send(embed=embed)

@bot.event
async def on_ready():
    print(f'🚀 Bot Listo: {bot.user}')
    for team_name in TEAMS.keys(): bot.add_view(VistaRuleta(team_name)) 
    if not tarea_herald.is_running(): tarea_herald.start()
    if not tarea_kupyo.is_running(): tarea_kupyo.start()
    if not tarea_cumples_fin_de_semana.is_running(): tarea_cumples_fin_de_semana.start()

# ==========================================
# COMANDOS MANUALES Y QA AUTOPILOT
# ==========================================

@bot.command(name="ruleta")
async def cmd_ruleta(ctx, equipo: str = None):
    if not equipo or equipo not in TEAMS:
        await ctx.send("⚠️ Indica un equipo: `!ruleta Kupyo` o `!ruleta Herald`")
        return
    await ejecutar_ruleta_equipo(equipo)

# --- COMANDOS CLICKUP (QA AUTOPILOT) ---

class DestinationSelect(Select):
    def __init__(self, options, task_id, task_data, ctx):
        discord_options = [discord.SelectOption(label=opt["label"], value=opt["value"]) for opt in options[:25]]
        super().__init__(placeholder="📂 Guardar tests en...", min_values=1, max_values=1, options=discord_options)
        self.task_id, self.task_data, self.ctx = task_id, task_data, ctx

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="🧠 La IA está pensando...", view=None)
        await self.generate_and_create(self.values[0])

    async def generate_and_create(self, list_id):
        try:
            is_backend = "[be]" in self.task_data["summary"].lower()
            sys_prompt = L.SYS_MSG_GENERATE_API_TESTS if is_backend else L.SYS_MSG_GENERATE_SCENARIOS
            scenarios, _ = await asyncio.to_thread(L.llm_generate_scenarios, issue_key=self.task_id, summary=self.task_data["summary"], full_context=self.task_data["full_context"], system_prompt=sys_prompt, images=self.task_data.get("images"), max_tests=50)

            if not scenarios: return await self.ctx.send("⚠️ No se generó nada.")
            msg = await self.ctx.send(f"✍️ Escribiendo **{len(scenarios)}** tests...")
            links = []
            for i, sc in enumerate(scenarios, 1):
                res = await asyncio.to_thread(C.create_test_task, self.task_id, f"TC{i:02d} | {self.task_id} | {sc['title']}", G.build_feature_single(self.task_data["summary"], self.task_id, sc), list_id)
                links.append(f"• [`TC{i:02d}`]({res.get('url')}) {sc['title']}")

            await msg.edit(content=f"🎉 **Tests creados para: {self.task_data['summary']}**\n\n" + "\n".join(links))
        except Exception as e: await self.ctx.send(f"🔥 Error: {e}")

@bot.command(name="clickup")
async def cmd_clickup(ctx, task_id: str):
    try:
        task_data = await asyncio.to_thread(C.get_task, task_id)
        lists = await asyncio.to_thread(C.get_testing_lists)
        await ctx.send(f"📂 Tarea: **{task_data['summary']}**", view=View().add_item(DestinationSelect(lists, task_id, task_data, ctx)))
    except Exception as e: await ctx.send(f"🔥 Error: {e}")

if __name__ == "__main__":
    if TOKEN: keep_alive(); bot.run(TOKEN)
