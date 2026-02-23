# src/discord_bot.py
import os
import asyncio
import discord
from discord.ext import commands
from discord.ui import Select, View
from dotenv import load_dotenv

from core import clickup as C
from core import llm as L
from core import gherkin as G
from core.clickup import find_test_case_type_id 

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'🚀 Bot Paginado Listo: {bot.user}')

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
                display_title = f"{tc_id} | {self.task_id} | {sc['title']}"
                
                link_text = f"• [`{tc_id}`]({url}) {sc['title']}"
                created_links.append(link_text)

            
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
            
            if current_chunk:
                await self.ctx.send(current_chunk)

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
        type_id_debug = C.find_test_case_type_id()
        print(f"DEBUG INICIAL: ID Type cargado: {type_id_debug}")

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

if __name__ == "__main__":
    if not TOKEN: print("❌ Falta TOKEN")
    else: bot.run(TOKEN)