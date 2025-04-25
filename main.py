import os
import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, InputText

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PANEL_CHANNEL_ID = int(os.getenv("PANEL_CHANNEL_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID"))

storage = {
    "drugs": 0,
    "dirty": 0,
    "clean": 0
}

leaderboard = {}

class ConfirmModal(Modal, title="Confirm Action"):
    amount = InputText(label="How many drugs are being taken?")
    money = InputText(label="How much money was deposited?")
    type = InputText(label="Type (clean or dirty)")
    target = InputText(label="Who is it for? (optional @mention)")

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        try:
            amt = int(self.amount.value.replace(',', ''))
            paid = int(self.money.value.replace(',', '').replace('£', ''))
            is_clean = "clean" in self.type.value.lower()
            target = self.target.value.strip()
            if target.startswith("<@") and target.endswith(">"):
                target_id = int(target[2:-1].replace("!", ""))
                member = interaction.guild.get_member(target_id)
                target_display = member.display_name if member else target
            else:
                member = None
                target_display = user.display_name

            storage["drugs"] -= amt
            storage["clean" if is_clean else "dirty"] += paid

            leaderboard.setdefault(target_display, {"drugs": 0, "paid": 0})
            leaderboard[target_display]["drugs"] += amt
            leaderboard[target_display]["paid"] += paid

            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            await log_channel.send(
                f"💊 {user.mention} - Take Drugs for {target_display}:\n"
                f"➤ Amount: `{amt}`\n➤ Paid: `£{paid}` ({'Clean' if is_clean else 'Dirty'})\n"
                f"\n📥 Storage:\n• Drugs: {storage['drugs']}\n• Dirty: £{storage['dirty']}\n• Clean: £{storage['clean']}"
            )
            await interaction.response.send_message("Logged successfully.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

class ButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Take Drugs", style=discord.ButtonStyle.primary, custom_id="take"))

    @discord.ui.button(label="Reset Leaderboard", style=discord.ButtonStyle.danger, custom_id="reset", row=1)
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message("You do not have permission.", ephemeral=True)
        leaderboard.clear()
        await interaction.response.send_message("Leaderboard has been reset.", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    await channel.purge(limit=5)
    await channel.send("📊 **Drop Panel**", view=ButtonView())

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type.name == "component":
        if interaction.data["custom_id"] == "take":
            await interaction.response.send_modal(ConfirmModal())
        elif interaction.data["custom_id"] == "reset":
            pass

bot.run(TOKEN)
