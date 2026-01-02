import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import io
from datetime import datetime, timedelta
from typing import Literal

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# File to store ticket configuration
CONFIG_FILE = "ticket_config.json"
TICKET_COUNTER_FILE = "ticket_counter.json"

# Default configuration
default_config = {
    "ticket_category": None,
    "transcript_channel": None,
    "support_roles": [],
    "ticket_type": "button",
    "ticket_message": None
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return default_config.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def load_ticket_counter():
    if os.path.exists(TICKET_COUNTER_FILE):
        with open(TICKET_COUNTER_FILE, 'r') as f:
            return json.load(f)
    return {"counter": 0}

def save_ticket_counter(counter_data):
    with open(TICKET_COUNTER_FILE, 'w') as f:
        json.dump(counter_data, f, indent=4)

config = load_config()

# ==================== TICKET SYSTEM ====================

class TicketButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.green, custom_id="create_ticket", emoji="🎫")
    async def create_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket(interaction)

class TicketDropdown(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.select(
        placeholder="Select a ticket type...",
        custom_id="ticket_dropdown",
        options=[
            discord.SelectOption(label="General Support", description="General questions and support", emoji="❓"),
            discord.SelectOption(label="Technical Issue", description="Report technical problems", emoji="⚙️"),
            discord.SelectOption(label="Report User", description="Report a user or issue", emoji="⚠️"),
            discord.SelectOption(label="Other", description="Other inquiries", emoji="💬")
        ]
    )
    async def ticket_dropdown(self, interaction: discord.Interaction, select: discord.ui.Select):
        await create_ticket(interaction, select.values[0])

class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket", emoji="🔒")
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await close_ticket(interaction)

async def create_ticket(interaction: discord.Interaction, ticket_type: str = "General"):
    config = load_config()
    
    if not config["ticket_category"]:
        await interaction.response.send_message("Ticket system is not configured yet!", ephemeral=True)
        return
    
    category = interaction.guild.get_channel(config["ticket_category"])
    if not category:
        await interaction.response.send_message("Ticket category not found!", ephemeral=True)
        return
    
    counter_data = load_ticket_counter()
    counter_data["counter"] += 1
    ticket_number = counter_data["counter"]
    save_ticket_counter(counter_data)
    
    ticket_name = f"ticket-{ticket_number}"
    
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    
    for role_id in config["support_roles"]:
        role = interaction.guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    
    ticket_channel = await category.create_text_channel(
        name=ticket_name,
        overwrites=overwrites
    )
    
    embed = discord.Embed(
        title=f"Ticket #{ticket_number}",
        description=f"**Type:** {ticket_type}\n**Created by:** {interaction.user.mention}\n\nThank you for creating a ticket! Support will be with you shortly.",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text=f"Ticket #{ticket_number}")
    
    await ticket_channel.send(embed=embed, view=TicketControls())
    await interaction.response.send_message(f"Ticket created! {ticket_channel.mention}", ephemeral=True)

async def close_ticket(interaction: discord.Interaction):
    config = load_config()
    
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message("This command can only be used in ticket channels!", ephemeral=True)
        return
    
    transcript = f"Transcript for {interaction.channel.name}\n"
    transcript += f"Closed by: {interaction.user}\n"
    transcript += f"Closed at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
    transcript += "="*50 + "\n\n"
    
    messages = []
    async for message in interaction.channel.history(limit=None, oldest_first=True):
        messages.append(message)
    
    for message in messages:
        transcript += f"[{message.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {message.author}: {message.content}\n"
        if message.attachments:
            for attachment in message.attachments:
                transcript += f"  [Attachment: {attachment.url}]\n"
        transcript += "\n"
    
    if config["transcript_channel"]:
        transcript_channel = interaction.guild.get_channel(config["transcript_channel"])
        if transcript_channel:
            transcript_bytes = io.BytesIO(transcript.encode('utf-8'))
            file = discord.File(fp=transcript_bytes, filename=f"{interaction.channel.name}-transcript.txt")
            
            embed = discord.Embed(
                title=f"Ticket Closed: {interaction.channel.name}",
                description=f"Closed by: {interaction.user.mention}",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            
            await transcript_channel.send(embed=embed, file=file)
    
    await interaction.response.send_message("Ticket will be closed in 5 seconds...", ephemeral=False)
    await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")

# ==================== TICKET SETUP COMMANDS ====================

@bot.tree.command(name="setup_ticket_category", description="Set the category where tickets will be created")
@app_commands.describe(category="The category for ticket channels")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket_category(interaction: discord.Interaction, category: discord.CategoryChannel):
    config = load_config()
    config["ticket_category"] = category.id
    save_config(config)
    await interaction.response.send_message(f"Ticket category set to: {category.name}", ephemeral=True)

@bot.tree.command(name="setup_transcript_channel", description="Set the channel where ticket transcripts will be sent")
@app_commands.describe(channel="The channel for transcripts")
@app_commands.checks.has_permissions(administrator=True)
async def setup_transcript_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    config = load_config()
    config["transcript_channel"] = channel.id
    save_config(config)
    await interaction.response.send_message(f"Transcript channel set to: {channel.mention}", ephemeral=True)

@bot.tree.command(name="add_support_role", description="Add a role that can access tickets")
@app_commands.describe(role="The support role")
@app_commands.checks.has_permissions(administrator=True)
async def add_support_role(interaction: discord.Interaction, role: discord.Role):
    config = load_config()
    if role.id not in config["support_roles"]:
        config["support_roles"].append(role.id)
        save_config(config)
        await interaction.response.send_message(f"Added {role.mention} as a support role!", ephemeral=True)
    else:
        await interaction.response.send_message(f"{role.mention} is already a support role!", ephemeral=True)

@bot.tree.command(name="remove_support_role", description="Remove a support role")
@app_commands.describe(role="The support role to remove")
@app_commands.checks.has_permissions(administrator=True)
async def remove_support_role(interaction: discord.Interaction, role: discord.Role):
    config = load_config()
    if role.id in config["support_roles"]:
        config["support_roles"].remove(role.id)
        save_config(config)
        await interaction.response.send_message(f"Removed {role.mention} from support roles!", ephemeral=True)
    else:
        await interaction.response.send_message(f"{role.mention} is not a support role!", ephemeral=True)

@bot.tree.command(name="ticket_button", description="Send a button to create tickets")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_button(interaction: discord.Interaction):
    config = load_config()
    config["ticket_type"] = "button"
    save_config(config)
    
    embed = discord.Embed(
        title="🎫 Support Tickets",
        description="Click the button below to create a support ticket!",
        color=discord.Color.blue()
    )
    
    await interaction.channel.send(embed=embed, view=TicketButton())
    await interaction.response.send_message("Ticket button sent!", ephemeral=True)

@bot.tree.command(name="ticket_dropdown", description="Send a dropdown menu to create tickets")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_dropdown(interaction: discord.Interaction):
    config = load_config()
    config["ticket_type"] = "dropdown"
    save_config(config)
    
    embed = discord.Embed(
        title="🎫 Support Tickets",
        description="Select a ticket type from the dropdown menu below!",
        color=discord.Color.blue()
    )
    
    await interaction.channel.send(embed=embed, view=TicketDropdown())
    await interaction.response.send_message("Ticket dropdown sent!", ephemeral=True)

# ==================== ROLE MANAGEMENT ====================

@bot.tree.command(name="addrole", description="Add a role to a user")
@app_commands.describe(member="The member to add the role to", role="The role to add")
@app_commands.checks.has_permissions(manage_roles=True)
async def addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message("I cannot add this role as it's higher than my highest role!", ephemeral=True)
        return
    
    if role in member.roles:
        await interaction.response.send_message(f"{member.mention} already has the {role.mention} role!", ephemeral=True)
        return
    
    await member.add_roles(role)
    await interaction.response.send_message(f"Added {role.mention} to {member.mention}!")

@bot.tree.command(name="removerole", description="Remove a role from a user")
@app_commands.describe(member="The member to remove the role from", role="The role to remove")
@app_commands.checks.has_permissions(manage_roles=True)
async def removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if role not in member.roles:
        await interaction.response.send_message(f"{member.mention} doesn't have the {role.mention} role!", ephemeral=True)
        return
    
    await member.remove_roles(role)
    await interaction.response.send_message(f"Removed {role.mention} from {member.mention}!")

# ==================== MODERATION COMMANDS ====================

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="The member to kick", reason="Reason for kicking")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if member.top_role >= interaction.guild.me.top_role:
        await interaction.response.send_message("I cannot kick this member!", ephemeral=True)
        return
    
    await member.kick(reason=reason)
    await interaction.response.send_message(f"Kicked {member.mention} | Reason: {reason}")

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="The member to ban", reason="Reason for banning")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if member.top_role >= interaction.guild.me.top_role:
        await interaction.response.send_message("I cannot ban this member!", ephemeral=True)
        return
    
    await member.ban(reason=reason)
    await interaction.response.send_message(f"Banned {member.mention} | Reason: {reason}")

@bot.tree.command(name="unban", description="Unban a user from the server")
@app_commands.describe(user_id="The ID of the user to unban")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"Unbanned {user.mention}")
    except:
        await interaction.response.send_message("Could not find user or unban failed!", ephemeral=True)

@bot.tree.command(name="timeout", description="Timeout a member")
@app_commands.describe(member="The member to timeout", duration="Duration in minutes", reason="Reason for timeout")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout_cmd(interaction: discord.Interaction, member: discord.Member, duration: int, reason: str = "No reason provided"):
    if member.top_role >= interaction.guild.me.top_role:
        await interaction.response.send_message("I cannot timeout this member!", ephemeral=True)
        return
    
    await member.timeout(timedelta(minutes=duration), reason=reason)
    await interaction.response.send_message(f"Timed out {member.mention} for {duration} minutes | Reason: {reason}")

@bot.tree.command(name="clear", description="Clear messages in a channel")
@app_commands.describe(amount="Number of messages to delete (max 100)")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    if amount > 100:
        await interaction.response.send_message("You can only delete up to 100 messages at once!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"Deleted {len(deleted)} messages!", ephemeral=True)

# ==================== UTILITY COMMANDS ====================

@bot.tree.command(name="serverinfo", description="Get information about the server")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    
    embed = discord.Embed(title=f"{guild.name} Server Information", color=discord.Color.blue())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="Server ID", value=guild.id, inline=True)
    embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="Created At", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="userinfo", description="Get information about a user")
@app_commands.describe(member="The member to get info about")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    
    embed = discord.Embed(title=f"{member} User Information", color=member.color)
    embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Roles", value=", ".join([r.mention for r in member.roles[1:]]) or "None", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ping", description="Check the bot's latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! Latency: {round(bot.latency * 1000)}ms")

# ==================== NEW COMMANDS ====================

@bot.tree.command(name="help", description="Show all available commands (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Bot Commands Help",
        description="Here are all available commands:",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="🎫 **Ticket System Setup**",
        value=(
            "`/setup_ticket_category` - Set the category where ticket channels will be created\n"
            "`/setup_transcript_channel` - Set the channel where ticket transcripts will be saved\n"
            "`/add_support_role` - Add a role that can view and manage tickets\n"
            "`/remove_support_role` - Remove a support role\n"
            "`/ticket_button` - Send a button in the current channel to create tickets\n"
            "`/ticket_dropdown` - Send a dropdown menu to create tickets with different types"
        ),
        inline=False
    )
    
    embed.add_field(
        name="👥 **Role Management**",
        value=(
            "`/addrole <member> <role>` - Add a role to a member\n"
            "`/removerole <member> <role>` - Remove a role from a member"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🛡️ **Moderation**",
        value=(
            "`/kick <member> [reason]` - Kick a member from the server\n"
            "`/ban <member> [reason]` - Ban a member from the server\n"
            "`/unban <user_id>` - Unban a user by their ID\n"
            "`/timeout <member> <minutes> [reason]` - Timeout a member for specified minutes\n"
            "`/clear <amount>` - Delete up to 100 messages in the current channel"
        ),
        inline=False
    )
    
    embed.add_field(
        name="ℹ️ **Utility**",
        value=(
            "`/serverinfo` - Display information about the server\n"
            "`/userinfo [member]` - Display information about a user\n"
            "`/ping` - Check the bot's latency\n"
            "`/activity <status> <type> <text>` - Change the bot's activity status\n"
            "`/dump` - Force sync all slash commands\n"
            "`/help` - Show this help message (Admin only)"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎟️ **Ticket Controls**",
        value=(
            "**In Ticket Channels:**\n"
            "🔒 `Close Ticket` button - Close the ticket and save transcript"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="activity", description="Change the bot's activity status")
@app_commands.describe(
    status="Bot status (online, idle, dnd, invisible)",
    activity_type="Type of activity",
    text="Activity text to display"
)
@app_commands.checks.has_permissions(administrator=True)
async def activity(
    interaction: discord.Interaction,
    status: Literal["online", "idle", "dnd", "invisible"],
    activity_type: Literal["playing", "streaming", "listening", "watching", "competing"],
    text: str
):
    status_map = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible
    }
    
    activity_map = {
        "playing": discord.ActivityType.playing,
        "streaming": discord.ActivityType.streaming,
        "listening": discord.ActivityType.listening,
        "watching": discord.ActivityType.watching,
        "competing": discord.ActivityType.competing
    }
    
    selected_status = status_map[status]
    selected_activity = discord.Activity(type=activity_map[activity_type], name=text)
    
    await bot.change_presence(status=selected_status, activity=selected_activity)
    
    status_emojis = {
        "online": "🟢",
        "idle": "🟡",
        "dnd": "🔴",
        "invisible": "⚫"
    }
    
    embed = discord.Embed(
        title="✅ Activity Changed",
        description=f"{status_emojis[status]} Status: **{status.capitalize()}**\n🎮 Activity: **{activity_type.capitalize()} {text}**",
        color=discord.Color.green()
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="dump", description="Force sync all slash commands (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def dump(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        synced = await bot.tree.sync()
        
        embed = discord.Embed(
            title="✅ Commands Synced",
            description=f"Successfully synced **{len(synced)}** slash commands!",
            color=discord.Color.green()
        )
        
        command_list = "\n".join([f"• `/{cmd.name}`" for cmd in synced])
        if len(command_list) > 1024:
            command_list = command_list[:1020] + "..."
        embed.add_field(name="Synced Commands:", value=command_list if command_list else "No commands", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"Commands dumped and synced: {len(synced)} commands")
        
    except Exception as e:
        embed = discord.Embed(
            title="❌ Sync Failed",
            description=f"Error syncing commands: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"Error syncing commands: {e}")

# ==================== BOT EVENTS ====================

@bot.event
async def on_ready():
    print(f"Bot is ready! Logged in as {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    
    bot.add_view(TicketButton())
    bot.add_view(TicketDropdown())
    bot.add_view(TicketControls())
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
        print(f"Commands: {[cmd.name for cmd in synced]}")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# Run the bot
bot.run('os.getenv('TOKEN')')
