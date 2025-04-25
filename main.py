import discord
from discord.ext import commands, tasks
from discord import ui
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("YOUR_BOT_TOKEN")
PANEL_CHANNEL_ID = int(os.getenv("PANEL_CHANNEL_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID"))
ALERT_USER_IDS = [int(uid.strip()) for uid in os.getenv("ALERT_USER_IDS", "").split(",") if uid.strip()]

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

storage = {
    "drugs": 0,
    "dirty": 0,
    "clean": 0
}

user_data = {}

def is_admin(interaction):
    return any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles)

class ConfirmModal(ui.Modal, title="Take Drugs"):
    drug_amount = ui.TextInput(label="How many drugs are being taken?", required=True)
    money_amount = ui.TextInput(label="How much money was deposited?", required=True)
    money_type = ui.TextInput(label="Type of money? (dirty/clean)", required=True)
    for_user = ui.TextInput(label="Who is this for? (leave blank for yourself)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            drugs = int(self.drug_amount.value)
            money = int(self.money_amount.value.replace(",", "").replace("£", ""))
            money_type = self.money_type.value.lower()
            target = self.for_user.value.strip() if self.for_user.value else interaction.user.display_name

            if money_type not in ["dirty", "clean"]:
                await interaction.response.send_message("❌ Invalid money type. Must be 'dirty' or 'clean'.", ephemeral=True)
                return

            if storage["drugs"] < drugs:
                await interaction.response.send_message("❌ Not enough drugs in storage.", ephemeral=True)
                return

            # Suspicious detection
            required_payment = drugs * 5000
            is_suspicious = money < required_payment
            alert_mentions = " ".join(f"<@{uid}>" for uid in ALERT_USER_IDS) if is_suspicious else ""

            # Update storage
            storage["drugs"] -= drugs

            # Log and track
            user_key = target.lower()
            if user_key not in user_data:
                user_data[user_key] = {"paid": 0, "taken": 0}
            user_data[user_key]["taken"] += drugs
            user_data[user_key]["paid"] += money

            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(
                    f"📦 {interaction.user.mention} - Take Drugs for **{target}**\n"
                    f"> Amount: **{drugs}**\n> Payment: £{money:,} ({money_type})\n\n"
                    f"🧾 Storage:\n• Drugs: {storage['drugs']}\n• Dirty: £{storage['dirty']:,}\n• Clean: £{storage['clean']:,}\n"
                    f"{'⚠️ Suspicious drop! ' + alert_mentions if is_suspicious else ''}"
                )
            await interaction.response.send_message(f"✅ Logged {drugs} drugs taken for {target}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

class DrugPanel(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Take Drugs", style=discord.ButtonStyle.blurple)
    async def take_drugs(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ConfirmModal())

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if channel:
        await channel.purge(limit=5)
        await channel.send("📊 **Drop Panel**", view=DrugPanel())
