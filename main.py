import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction, Embed
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("YOUR_BOT_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID"))
PANEL_CHANNEL_ID = int(os.getenv("PANEL_CHANNEL_ID"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID"))

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

leaderboard = {}

class DropPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Take Drugs", style=discord.ButtonStyle.primary)
    async def take_drugs(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TakeDrugsModal())

    @discord.ui.button(label="Deposit Dirty Money", style=discord.ButtonStyle.success)
    async def deposit_dirty(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DepositMoneyModal("dirty"))

    @discord.ui.button(label="Deposit Clean Money", style=discord.ButtonStyle.success)
    async def deposit_clean(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DepositMoneyModal("clean"))

    @discord.ui.button(label="Set Drugs (Admin Only)", style=discord.ButtonStyle.secondary)
    async def set_drugs(self, interaction: Interaction, button: discord.ui.Button):
        if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("You don't have permission to use this button.", ephemeral=True)
            return
        await interaction.response.send_modal(SetDrugsModal())

    @discord.ui.button(label="Remove All Money (Admin Only)", style=discord.ButtonStyle.danger)
    async def remove_all_money(self, interaction: Interaction, button: discord.ui.Button):
        if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("You don't have permission to use this button.", ephemeral=True)
            return
        storage["dirty"] = 0
        storage["clean"] = 0
        await interaction.response.send_message("💸 All money removed.", ephemeral=True)
        await update_leaderboard()

    @discord.ui.button(label="Reset Leaderboard (Admin Only)", style=discord.ButtonStyle.danger)
    async def reset_leaderboard(self, interaction: Interaction, button: discord.ui.Button):
        if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("You don't have permission to use this button.", ephemeral=True)
            return
        leaderboard.clear()
        await interaction.response.send_message("Leaderboard has been reset.", ephemeral=True)
        await update_leaderboard()

class TakeDrugsModal(discord.ui.Modal, title="Take Drugs"):
    drug_amount = discord.ui.TextInput(label="Drugs Taken", required=True)
    money_amount = discord.ui.TextInput(label="Money Deposited", required=True)
    money_type = discord.ui.TextInput(label="Money Type (dirty/clean)", required=True)
    for_user = discord.ui.TextInput(label="@User or leave blank for self", required=False)

    async def on_submit(self, interaction: Interaction):
        user = interaction.user
        target = self.for_user.value if self.for_user.value else user.mention
        try:
            drugs = int(self.drug_amount.value)
            money = int(self.money_amount.value)
            mtype = self.money_type.value.lower()
            if mtype not in ["dirty", "clean"]:
                raise ValueError("Invalid money type")

            # Check
            if drugs > storage["drugs"]:
                await interaction.response.send_message("Not enough drugs in storage.", ephemeral=True)
                return
            if money < drugs * 5000:
                alert_ids = os.getenv("ALERT_USER_IDS", "").split(",")
                mentions = " ".join(f"<@{uid.strip()}>" for uid in alert_ids if uid.strip())
                await interaction.channel.send(f"🚨 {mentions} Suspicious drop: {user.mention} only paid £{money:,} for {drugs} drugs.")

            # Log and adjust
            storage["drugs"] -= drugs
            storage[mtype] += money
            leaderboard.setdefault(target, {"in": 0, "out": 0, "drugs": 0})
            leaderboard[target]["out"] += money
            leaderboard[target]["drugs"] += drugs

            await interaction.response.send_message(f"✅ {user.mention} took {drugs} drugs for {target} and deposited £{money:,} {mtype}.")
            await update_leaderboard()
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

class DepositMoneyModal(discord.ui.Modal):
    def __init__(self, mtype):
        super().__init__(title=f"Deposit {mtype.title()} Money")
        self.mtype = mtype
        self.amount = discord.ui.TextInput(label="Amount", required=True)
        self.add_item(self.amount)

    async def on_submit(self, interaction: Interaction):
        user = interaction.user
        try:
            amount = int(self.amount.value)
            storage[self.mtype] += amount
            leaderboard.setdefault(user.display_name, {"in": 0, "out": 0, "drugs": 0})
            leaderboard[user.display_name]["in"] += amount
            await interaction.response.send_message(f"💸 {user.mention} deposited £{amount:,} {self.mtype}.")
            await update_leaderboard()
        except:
            await interaction.response.send_message("❌ Invalid amount.", ephemeral=True)

class SetDrugsModal(discord.ui.Modal, title="Set Total Drugs"):
    amount = discord.ui.TextInput(label="Drugs in storage", required=True)

    async def on_submit(self, interaction: Interaction):
        try:
            amt = int(self.amount.value)
            storage["drugs"] = amt
            await interaction.response.send_message(f"💊 Drugs in storage set to {amt}.")
            await update_leaderboard()
        except:
            await interaction.response.send_message("❌ Invalid input.", ephemeral=True)

async def update_leaderboard():
    try:
        channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if channel:
            sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1]["in"], reverse=True)
            desc = "\n".join([
                f"**{name}** - Paid: £{data['in']:,}, Taken: £{data['out']:,}, Drugs: {data['drugs']}"
                for name, data in sorted_lb
            ])
            total = f"\n\n**Storage Totals:**\n• Drugs: {storage['drugs']}\n• Dirty: £{storage['dirty']:,}\n• Clean: £{storage['clean']:,}"
            embed = Embed(title="💊 Drug Leaderboard", description=desc + total)
            await channel.purge(limit=10)
            await channel.send(embed=embed)
    except Exception as e:
        print("Leaderboard error:", e)

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if channel:
        await channel.purge(limit=5)
        await channel.send("📊 **Drop Panel**", view=DropPanel())
    await update_leaderboard()

bot.run(TOKEN)
