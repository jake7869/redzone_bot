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
COUNT_FILE = "redzone_count.json"
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
redzone_count = load_json(COUNT_FILE, {"count": 1})["count"]
redzone_logs = load_json(LOG_FILE, [])
leaderboard_message = None
active_redzone_messages = []

class PermanentRedzoneView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Start Redzone", style=discord.ButtonStyle.primary, custom_id="start_redzone_button")
    async def start_redzone(self, interaction: discord.Interaction, button: Button):
        global redzone_count
        view = RedzoneView(redzone_number=redzone_count)
        embed = discord.Embed(
            title=f"🚨 Join Redzone {redzone_count}!",
            description="You have 6 minutes.\n\n👥 Joined: _None yet_",
            color=discord.Color.red()
        )
        msg = await interaction.channel.send(embed=embed, view=view)
        view.set_message(msg)
        active_redzone_messages.append(msg)
        await view.start_outcome_prompt(interaction.guild, interaction.channel)
        redzone_count += 1
        save_json(COUNT_FILE, {"count": redzone_count})

class RedzoneView(View):
    def __init__(self, redzone_number):
        super().__init__(timeout=None)
        self.redzone_number = redzone_number
        self.joined_users = set()
        self.message = None
        self.closed = False

    def set_message(self, message):
        self.message = message

    async def update_joined_embed(self, guild):
        names = [f"<@{uid}>" for uid in self.joined_users]
        name_list = ", ".join(names) if names else "_None yet_"
        embed = discord.Embed(
            title=f"🚨 Join Redzone {self.redzone_number}!",
            description=f"You have 6 minutes.\n\n👥 Joined: {name_list}",
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
        await interaction.followup.send(f"✅ You've joined Redzone {self.redzone_number}!", ephemeral=True)

    async def start_outcome_prompt(self, guild, channel):
        await asyncio.sleep(360)
        participants = list(self.joined_users)
        rn = self.redzone_number

        class OutcomeView(View):
            def __init__(self):
                super().__init__(timeout=None)

            @discord.ui.button(label="Win", style=discord.ButtonStyle.success)
            async def win(self, interaction: discord.Interaction, button: Button):
                await handle_redzone_end("win", participants, rn, guild, channel, interaction)

            @discord.ui.button(label="Lose", style=discord.ButtonStyle.danger)
            async def lose(self, interaction: discord.Interaction, button: Button):
                await handle_redzone_end("loss", participants, rn, guild, channel, interaction)

        msg = await channel.send(f"⏳ Redzone {rn} over. Was it a win or a loss?", view=OutcomeView())
        active_redzone_messages.append(msg)

async def handle_redzone_end(result, participants, redzone_number, guild, channel, interaction):
    for view_message in active_redzone_messages:
        try:
            for component in view_message.components:
                for child in component.children:
                    child.disabled = True
            await view_message.edit(view=view_message.components[0].view if view_message.components else None)
        except:
            pass

    if result == "win" and participants:
        split = WIN_AMOUNT // len(participants)
        log_entry = {"redzone": redzone_number, "result": "win", "split": split, "participants": []}
        for uid in participants:
            uid_str = str(uid)
            redzone_data[uid_str]["wins"] += 1
            redzone_data[uid_str]["earned"] += split
            log_entry["participants"].append(uid_str)
        redzone_logs.append(log_entry)
        save_json(DATA_FILE, redzone_data)
        save_json(LOG_FILE, redzone_logs)
        await update_leaderboard(guild)
        await interaction.response.edit_message(content=f"✅ Redzone {redzone_number} marked as a **WIN**! Each participant gets £{split:,}.", view=None)
    else:
        redzone_logs.append({"redzone": redzone_number, "result": "loss", "participants": [str(uid) for uid in participants]})
        save_json(LOG_FILE, redzone_logs)
        await interaction.response.edit_message(content=f"❌ Redzone {redzone_number} marked as a **LOSS**. No payout.", view=None)

    await cleanup_redzone_messages(channel)

async def cleanup_redzone_messages(channel):
    await asyncio.sleep(2)
    messages = await channel.history(limit=100).flatten()
    for msg in messages:
        if msg.id != leaderboard_message.id and not any(btn.custom_id == "start_redzone_button" for btn in getattr(msg.components[0], "children", [])):
            try:
                await msg.delete()
            except:
                pass
    active_redzone_messages.clear()

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
