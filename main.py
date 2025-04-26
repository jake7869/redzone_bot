import discord
from discord.ext import commands
from discord.ui import Button, View
import asyncio
import os
import json

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = 1359223780857217246
LEADERBOARD_CHANNEL_ID = 1359223780857217246
ADMIN_ROLE_ID = 1300916696860856448
WIN_AMOUNT = 250_000

DATA_FILE = "redzone_data.json"
LOG_FILE = "redzone_log.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return default

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

redzone_data = load_json(DATA_FILE, {})
joined_users = set(redzone_data.keys())
redzone_logs = load_json(LOG_FILE, [])
leaderboard_message = None
active_redzones = {}  # postal -> list of messages

class PermanentRedzoneView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Start Redzone", style=discord.ButtonStyle.primary, custom_id="start_redzone_button")
    async def start_redzone(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("📍 Please enter the postal code for this Redzone (reply below):", ephemeral=True)

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await bot.wait_for("message", timeout=30.0, check=check)
            postal_code = msg.content.strip()

            view = RedzoneView(postal_code=postal_code)
            embed = discord.Embed(
                title=f"🚨 Redzone at Postal: {postal_code}",
                description="You have 4 minutes 30 seconds.\n\n👥 Joined: _None yet_",
                color=discord.Color.red()
            )
            redzone_channel = interaction.guild.get_channel(CHANNEL_ID)
            posted_msg = await redzone_channel.send(embed=embed, view=view)
            view.set_message(posted_msg)
            active_redzones[postal_code] = [posted_msg]
            await view.start_outcome_prompt(interaction.guild, redzone_channel)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Redzone creation cancelled (no postal provided).", ephemeral=True)

class RedzoneView(View):
    def __init__(self, postal_code):
        super().__init__(timeout=None)
        self.postal_code = postal_code
        self.joined_users = set()
        self.message = None
        self.closed = False

    def set_message(self, message):
        self.message = message

    async def update_joined_embed(self, guild):
        names = [f"<@{uid}>" for uid in self.joined_users]
        name_list = ", ".join(names) if names else "_None yet_"
        embed = discord.Embed(
            title=f"🚨 Redzone at Postal: {self.postal_code}",
            description=f"You have 4 minutes 30 seconds.\n\n👥 Joined: {name_list}",
            color=discord.Color.red()
        )
        await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Join Redzone", style=discord.ButtonStyle.success, custom_id="join_redzone_button")
    async def join(self, interaction: discord.Interaction, button: Button):
        if self.closed:
            await interaction.response.send_message("❌ This redzone is closed.", ephemeral=True)
            return

        self.joined_users.add(interaction.user.id)

        uid_str = str(interaction.user.id)
        joined_users.add(uid_str)

        if uid_str not in redzone_data:
            redzone_data[uid_str] = {"joined": 0, "wins": 0, "earned": 0}

        redzone_data[uid_str]["joined"] += 1
        save_json(DATA_FILE, redzone_data)

        await interaction.response.defer(ephemeral=True)
        await self.update_joined_embed(interaction.guild)
        await update_leaderboard(interaction.guild)
        await interaction.followup.send(f"✅ You've joined Redzone at Postal: {self.postal_code}!", ephemeral=True)

    async def start_outcome_prompt(self, guild, channel):
        await asyncio.sleep(270)  # ⏰ 4 minutes 30 seconds
        participants = list(self.joined_users)

        class OutcomeView(View):
            def __init__(self):
                super().__init__(timeout=None)

            @discord.ui.button(label="Win", style=discord.ButtonStyle.success)
            async def win(self, interaction: discord.Interaction, button: Button):
                await interaction.response.defer()  # ✅ prevent interaction failed
                await handle_redzone_end(self.postal_code, "win", participants, guild, channel, interaction)

            @discord.ui.button(label="Lose", style=discord.ButtonStyle.danger)
            async def lose(self, interaction: discord.Interaction, button: Button):
                await interaction.response.defer()  # ✅ prevent interaction failed
                await handle_redzone_end(self.postal_code, "loss", participants, guild, channel, interaction)

        msg = await channel.send(f"⏳ Redzone at Postal {self.postal_code} is over. Was it a win or a loss?", view=OutcomeView())
        active_redzones[self.postal_code].append(msg)

async def handle_redzone_end(postal_code, result, participants, guild, channel, interaction):
    for msg in active_redzones.get(postal_code, []):
        try:
            for comp in msg.components:
                for child in comp.children:
                    child.disabled = True
            await msg.edit(view=msg.components[0].view if msg.components else None)
        except:
            pass

    await asyncio.sleep(1)
    for msg in active_redzones.get(postal_code, []):
        try:
            await msg.delete()
        except:
            pass
    active_redzones.pop(postal_code, None)

    if result == "win" and participants:
        split = WIN_AMOUNT // len(participants)
        for uid in participants:
            uid_str = str(uid)
            redzone_data[uid_str]["wins"] += 1
            redzone_data[uid_str]["earned"] += split
        save_json(DATA_FILE, redzone_data)
        await update_leaderboard(guild)
        await channel.send(f"✅ Redzone at Postal {postal_code} marked as a **WIN**! Each participant gets £{split:,}.")
    else:
        await channel.send(f"❌ Redzone at Postal {postal_code} marked as a **LOSS**. No payout.")

class ResetView(View):
    @discord.ui.button(label="Payout & Reset", style=discord.ButtonStyle.danger)
    async def reset(self, interaction: discord.Interaction, button: Button):
        if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("❌ You don't have permission to reset the leaderboard.", ephemeral=True)
            return
        redzone_data.clear()
        joined_users.clear()
        save_json(DATA_FILE, redzone_data)
        await update_leaderboard(interaction.guild)
        await interaction.response.send_message("✅ Leaderboard has been reset!", ephemeral=True)

async def update_leaderboard(guild):
    global leaderboard_message
    channel = guild.get_channel(LEADERBOARD_CHANNEL_ID)

    all_data = {
        uid: redzone_data.get(uid, {"joined": 0, "wins": 0, "earned": 0})
        for uid in joined_users
    }
    leaderboard = sorted(all_data.items(), key=lambda x: x[1]["earned"], reverse=True)

    desc = ""
    sus_section = ""
    for uid, stats in leaderboard:
        member = guild.get_member(int(uid))
        if not member:
            continue
        desc += f"<@{uid}> — £{stats['earned']:,} ({stats['joined']} joins / {stats['wins']} wins)\n"
        if stats["joined"] >= 3 and stats["wins"] == 0:
            sus_section += f"🚨 <@{uid}> — {stats['joined']} joins / {stats['wins']} wins\n"

    if sus_section:
        desc += f"\n__**Sus Players**__\n{sus_section}"

    embed = discord.Embed(
        title="🏆 Redzone Earnings Leaderboard",
        description=desc or "No participants yet.",
        color=0x00ff00
    )

    if leaderboard_message:
        await leaderboard_message.edit(embed=embed)
    else:
        leaderboard_message = await channel.send(embed=embed, view=ResetView())

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    guild = bot.guilds[0]
    redzone_channel = guild.get_channel(CHANNEL_ID)

    view = PermanentRedzoneView()
    await update_leaderboard(guild)
    await redzone_channel.send("🔘 Use the button below to start a Redzone round:", view=view)

bot.run(TOKEN)
