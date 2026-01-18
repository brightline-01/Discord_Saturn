import discord
from discord.ext import commands
import json
import os
import datetime
import re

ticket_settings_file = "ticket_settings.json"

class ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketView(self.bot))
        if discord.NotFound:
            pass
        print("[Ticket] 서버 별 티켓 설정 파일을 로드했습니다.")

    Ticket = discord.SlashCommandGroup("티켓")

    @Ticket.command(name="설정", description="티켓 생성용 메세지를 설정합니다. 서버 소유자 권한을 요구합니다.", options=[
        discord.Option(discord.Role, name="역할", description="티켓을 관리할 역할"),
        discord.Option(discord.CategoryChannel, name="생성", description="티켓이 생성될 카테고리"),
        discord.Option(discord.CategoryChannel, name="보관", description="티켓이 보관될 카테고리"),
        discord.Option(discord.TextChannel, name="아카이브", description="티켓 아카이브를 전송할 채널", required=False)
    ])
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx, support_role: discord.Role, ticket_category: discord.CategoryChannel, closed_category: discord.CategoryChannel, log_channel: discord.TextChannel):
        settings = {}
        if os.path.exists(ticket_settings_file):
            with open(ticket_settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)

        settings[str(ctx.guild.id)] = {
            "support_role": support_role.id,
            "ticket_category": ticket_category.id,
            "closed_category": closed_category.id,
            "log_channel": log_channel.id if log_channel else None
        }

        with open(ticket_settings_file, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)

        view = TicketView(self.bot)
        embed = discord.Embed(title="🎫 서버 문의", description="아래 버튼을 눌러 티켓을 생성하세요.", color=discord.Color.blue())
        await ctx.channel.send(embed=embed, view=view)
        await ctx.respond(embed=discord.Embed(description=f":white_check_mark: 티켓 설정이 완료되었습니다."), ephemeral=True)
        print(f"[Command | Ticket] 사용자가 티켓을 설정했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    @Ticket.command(name="초기화", description="닫힌 모든 티켓을 삭제합니다. 관리자 권한을 요구합니다.")
    @commands.has_permissions(administrator=True)
    async def delete_all_closed_tickets(self, ctx: discord.ApplicationContext):
        deleted_count = 0

        for channel in ctx.guild.text_channels:
            if channel.name.startswith("closed-"):
                try:
                    await channel.delete(reason=f"Delete all closed tickets by {ctx.author}")
                    deleted_count += 1
                except:
                    continue

        await ctx.respond(embed=discord.Embed(description=f":white_check_mark: 닫힌 티켓 {deleted_count}개를 삭제했습니다."), ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    def get_next_ticket_number(self, guild: discord.Guild):
        ticket_numbers = []

        for channel in guild.text_channels:
            if channel.name.startswith("ticket-"):
                try:
                    number = int(channel.name.replace("ticket-", ""))
                    ticket_numbers.append(number)
                except ValueError:
                    continue

        if ticket_numbers:
            next_number = max(ticket_numbers) + 1
        else:
            next_number = 1

        return next_number

    @discord.ui.button(label="🎫 티켓 열기", style=discord.ButtonStyle.green, custom_id="create_ticket")
    async def create_ticket(self, button: discord.ui.Button, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        open_member = interaction.user

        with open(ticket_settings_file, "r", encoding="utf-8") as f:
            settings = json.load(f)
        guild_settings = settings.get(str(guild.id))
        if not guild_settings:
            return await interaction.response.send_message(embed=discord.Embed(description=":warning: 티켓 설정이 완료되지 않았습니다. 서버 관리자에게 문의하세요."), ephemeral=True)

        support_role = guild.get_role(guild_settings["support_role"])
        ticket_category = guild.get_channel(guild_settings["ticket_category"])
        closed_category = guild.get_channel(guild_settings["closed_category"])
        log_channel = guild.get_channel(guild_settings["log_channel"]) if guild_settings.get("log_channel") else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        ticket_number = self.get_next_ticket_number(guild)
        channel_name = f"ticket-{ticket_number:04d}"

        channel = await guild.create_text_channel(
            name=channel_name,
            category=ticket_category,
            overwrites=overwrites,
            reason=f"Ticket #{ticket_number} opened by {member}"
        )
        self.save_ticket(guild.id, ticket_number, member.id, channel.id, closed_category.id, log_channel.id if log_channel else None)

        mention_roles = []
        bot_roles = set()
        for member in guild.members:
            if member.bot:
                bot_roles.update(member.roles)

        if support_role:
            mention_roles.append(support_role)

        for role in guild.roles:
            if role.permissions.administrator and role != guild.default_role and role not in bot_roles:
                mention_roles.append(role)

        mention_text = ", ".join(role.mention for role in mention_roles) if mention_roles else None

        embed = discord.Embed(title="🎫 티켓이 생성되었습니다.", description=f"{open_member.mention}님, 문의사항을 입력해주세요. {mention_text}이(가) 해결해 드리겠습니다.", color=discord.Color.blue())
        await channel.send(embed=embed, view=CloseTicketView(channel, guild.id, support_role.id if support_role else None))

        await interaction.response.send_message(embed=discord.Embed(description=f":white_check_mark: {channel.mention} 티켓을 생성했습니다."), ephemeral=True)
        print(f"[Command | Ticket] 사용자가 티켓을 생성했습니다. (서버: {interaction.guild.name}, 사용자: {open_member.display_name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    def save_ticket(self, guild_id, number, user_id, channel_id, closed_category_id, log_channel_id):
        data = {}
        if os.path.exists("ticket_data.json"):
            with open("ticket_data.json", "r", encoding="utf-8") as f:
                data = json.load(f)
        guild_key = str(guild_id)
        if guild_key not in data:
            data[guild_key] = {"last_ticket": number, "tickets": {}}
        data[guild_key]["tickets"][str(number)] = {
            "user": user_id,
            "channel": channel_id,
            "closed_category": closed_category_id,
            "log_channel": log_channel_id
        }
        with open("ticket_data.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

class CloseTicketView(discord.ui.View):
    def __init__(self, channel, guild_id, support_role_id=None):
        super().__init__(timeout=None)
        self.channel = channel
        self.guild_id = guild_id
        self.support_role_id = support_role_id

    @discord.ui.button(label="🔒 티켓 닫기 (관리자 전용)", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, button: discord.ui.Button, interaction: discord.Interaction):
        channel_name = interaction.channel.name
        match = re.search(r'\d+', channel_name)
        ticket_number = int(match.group()) if match else None

        with open("ticket_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        ticket_info = data[str(self.guild_id)]["tickets"].get(str(ticket_number))
        if not ticket_info:
            return await interaction.response.send_message(embed=discord.Embed(description=":warning: 티켓 정보를 찾을 수 없습니다."), ephemeral=True)

        user_roles = [role.id for role in interaction.user.roles]
        is_admin = any(role.permissions.administrator for role in interaction.user.roles)
        has_support = self.support_role_id in user_roles if self.support_role_id else False

        if not (is_admin or has_support):
            return await interaction.response.send_message(embed=discord.Embed(description=":warning: 티켓 관리 권한이 없습니다."), ephemeral=True)

        closed_category = interaction.guild.get_channel(ticket_info["closed_category"])
        log_channel = interaction.guild.get_channel(ticket_info["log_channel"]) if ticket_info.get("log_channel") else None

        if closed_category:
            new_channel_name = interaction.channel.name.replace("ticket-", "closed-", 1)
            await interaction.channel.edit(category=closed_category, name=new_channel_name, reason=f"Ticket #{ticket_number} closed")

        messages = []
        async for msg in self.channel.history(limit=None, oldest_first=True):
            timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            messages.append(f"[{timestamp}] {msg.author.display_name}({msg.author.name}): {msg.content}")
        log_text = "\n".join(messages)

        if log_channel:
            import io
            await log_channel.send(
                content=f":white_check_mark: {channel_name}의 아카이브입니다.",
                file=discord.File(io.StringIO(log_text), filename=f"{self.channel.name}.txt")
            )

        overwrites = self.channel.overwrites
        for target in overwrites:
            overwrites[target].view_channel = False
        await self.channel.edit(overwrites=overwrites)

        del data[str(self.guild_id)]["tickets"][str(ticket_number)]
        with open("ticket_data.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        await interaction.response.send_message(embed=discord.Embed(description=":white_check_mark: 티켓을 닫고 비공개로 설정했습니다. 아래 버튼을 눌러 티켓을 삭제할 수 있습니다.", view=DeleteTicketView(self.channel, self.guild_id, self.support_role_id)))
        print(f"[Command | Ticket] 사용자가 티켓을 보관했습니다. (서버: {interaction.guild.name}, 요청자: {interaction.user.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

class DeleteTicketView(discord.ui.View):
    def __init__(self, channel, guild_id, support_role_id=None):
        super().__init__(timeout=None)
        self.channel = channel
        self.guild_id = guild_id
        self.support_role_id = support_role_id

    @discord.ui.button(label="🗑️ 티켓 삭제", style=discord.ButtonStyle.danger, custom_id="delete_ticket")
    async def close_ticket(self, button: discord.ui.Button, interaction: discord.Interaction):
        user_roles = [role.id for role in interaction.user.roles]
        is_admin = any(role.permissions.administrator for role in interaction.user.roles)
        has_support = self.support_role_id in user_roles if self.support_role_id else False
    
        if not (is_admin or has_support):
            return await interaction.response.send_message(embed=discord.Embed(description=":warning: 티켓 관리 권한이 없습니다."), ephemeral=True)

        channel_name = interaction.channel.name
        match = re.search(r'\d+', channel_name)
        ticket_number = int(match.group()) if match else None

        await interaction.channel.delete(reason=f"Channel deleted by {interaction.user}")
        print(f"[Command | Ticket] 사용자가 티켓을 삭제했습니다. (서버: {interaction.guild.name}, 요청자: {interaction.user.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

        with open("ticket_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        ticket_info = data[str(self.guild_id)]["tickets"].get(str(ticket_number))

        if ticket_info:
            del data[str(self.guild_id)]["tickets"][str(ticket_number)]
            with open("ticket_data.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

def setup(bot):
    bot.add_cog(ticket(bot))