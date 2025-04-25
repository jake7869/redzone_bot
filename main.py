import discord
from discord.ext import commands
from discord.ui import Button, View
import asyncio
import os
import json

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = 1359223780857217246
ADMIN_ROLE_ID = 1300916696860856448
WIN_AMOUNT = 250_000
DATA_FILE = "redzone_data.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Load or initialize redzone earnings
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

redzone_earnings = load_data()
leaderboard_message = None

class PermanentRedzoneView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Start Redzone", style=discord.ButtonStyle.primary, custom_id="start_redzone_button")
    async def start_redzone(self, interaction: discord.Interaction, button: Button):
        view = RedzoneView()
        await interaction.channel.send("🚨 Redzone Started! Click below to join. You have 6 minutes.", view=view)
        await view.start_outcome_prompt(interaction.guild, interaction.channel)

class RedzoneView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.joined_users = set()

    @discord.ui.button(label="Join Redzone", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: Button):
        self.joined_users.add(interaction.user.id)
        await interaction.response.send_message("✅ You've joined the redzone!", ephemeral=True)

    async def start_outcome_prompt(self, guild, channel):
        await asyncio.sleep(360)

        class OutcomeView(View):
            @discord.ui.button(label="Win", style=discord.ButtonStyle.success)
            async def win(self, interaction: discord.Interaction, button: Button):
                if not self.view.joined_users:
                    await interaction.response.send_message("❌ No participants to reward.", ephemeral=True)
                    return
                split = WIN_AMOUNT // len(self.view.joined_users)
                for uid in self.view.joined_users:
                    redzone_earnings[str(uid)] = redzone_earnings.get(str(uid), 0) + split
                save_data(redzone_earnings)
                await update_leaderboard(guild)
                await interaction.response.edit_message(content=f"✅ Redzone marked as a **WIN**! Each participant gets £{split:,}.", view=None)

            @discord.ui.button(label="Lose", style=discord.ButtonStyle.danger)
            async def lose(self, interaction: discord.Interaction, button: Button):
                await interaction.response.edit_message(content="❌ Redzone marked as a **LOSS**. No payout.", view=None)

        await channel.send("⏳ Redzone over. Was it a win or a loss?", view=OutcomeView())

class ResetView(View):
    @discord.ui.button(label="Payout & Reset", style=discord.ButtonStyle.danger)
    async def reset(self, interaction: discord.Interaction, button: Button):
        if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("❌ You don't have permission to reset the leaderboard.", ephemeral=True)
            return
        redzone_earnings.clear()
        save_data(redzone_earnings)
        await update_leaderboard(interaction.guild)
        await interaction.response.send_message("✅ Leaderboard has been reset!", ephemeral=True)

async def update_leaderboard(guild):
    global leaderboard_message
    channel = guild.get_channel(CHANNEL_ID)
    leaderboard = sorted(redzone_earnings.items(), key=lambda x: x[1], reverse=True)
    desc = ""
    for uid, amt in leaderboard:
        user = guild.get_member(int(uid))
        if user:
            desc += f"<@{uid}> - £{amt:,}\\n"
    embed = discord.Embed(title="🏆 Redzone Earnings Leaderboard", description=desc or "No data yet.", color=0x00ff00)

    if leaderboard_message:
        await leaderboard_message.edit(embed=embed)
    else:
        leaderboard_message = await channel.send(embed=embed, view=ResetView())

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    guild = bot.guilds[0]
    channel = guild.get_channel(CHANNEL_ID)

    view = PermanentRedzoneView()
    await update_leaderboard(guild)
    await channel.send("🔘 Use the button below to start a Redzone round:", view=view)

bot.run(TOKEN)
