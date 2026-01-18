import discord
import datetime
import re
from discord.ext import commands

class moderate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    Moderate = discord.SlashCommandGroup("관리")

    @Moderate.command(name="추방", description="사용자를 서버에서 추방합니다. 멤버 추방 권한을 요구합니다.", options=[
        discord.Option(discord.Member, name="사용자", description="추방할 사용자", required=True),
        discord.Option(str, name="사유", description="추방할 사유 (선택)", required=False)])
    @discord.default_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "사유 없음"):
        if member == self.bot.user:
            return await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션이 스스로를 추방할 수 없습니다."), ephemeral=True)
        try:
            await member.kick(reason=reason)
            embed = discord.Embed(title=f":warning: {member.display_name}님을 서버에서 추방했습니다.", color=discord.Color.red())
            embed.add_field(name="사유", value=reason if reason else "사유 없음", inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.avatar)
            embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await ctx.respond(embed=embed)
            print(f"[Command | Moderate] 사용자를 추방했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 추방한 사용자: {member.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except discord.Forbidden:
            await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션에게 멤버 추방 권한이 없거나 추방할 사용자의 역할이 애플리케이션의 역할보다 높습니다. 서버 소유자 또는 관리자에게 문의해주세요.", color=discord.Color.red()), ephemeral=True)
    @kick.error
    async def kick_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.respond(embed=discord.Embed(description=":warning: 사용자를 찾을 수 없습니다. 올바른 사용자 이름, 멘션 또는 ID를 입력해주세요."), ephemeral=True)
        elif isinstance(error, commands.MissingPermissions):
            await ctx.respond(embed=discord.Embed(description=":warning: 사용자에게 멤버 추방 권한이 없습니다."), ephemeral=True)

    @Moderate.command(name="차단", description="사용자를 서버에서 차단합니다. 멤버 차단 권한을 요구합니다.", options=[
        discord.Option(discord.Member, name="사용자", description="차단할 사용자", required=True),
        discord.Option(str, name="사유", description="차단할 사유 (선택)", required=False)])
    @discord.default_permissions(kick_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "사유 없음"):
        if member == self.bot.user:
            return await ctx.send(embed=discord.Embed(description=":warning: 애플리케이션이 스스로를 차단할 수 없습니다."), ephemeral=True)
        try:
            await member.ban(reason=reason)
            embed = discord.Embed(title=f":hammer_pick: {member.display_name}님을 서버에서 차단했습니다.", color=discord.Color.red())
            embed.add_field(name="사유", value=reason if reason else "사유 없음", inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.avatar)
            embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await ctx.respond(embed=embed)
            print(f"[Command | Moderate] 사용자를 차단했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 차단한 사용자: {member.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except discord.Forbidden:
            await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션에게 멤버 차단하기 권한이 없거나 차단할 사용자의 역할이 애플리케이션의 역할보다 높습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
    @ban.error
    async def ban_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.respond(embed=discord.Embed(description=":warning: 사용자를 찾을 수 없습니다. 올바른 사용자 이름, 멘션 또는 ID를 입력해주세요."), ephemeral=True)
        elif isinstance(error, commands.MissingPermissions):
            await ctx.respond(embed=discord.Embed(description=":warning: 사용자에게 멤버 차단하기 권한이 없습니다."), ephemeral=True)

    Timeout = Moderate.create_subgroup("타임아웃", "타임아웃 부여/해제 명령어입니다.")

    @Timeout.command(name="부여", description="사용자를 지정한 시간 동안 타임아웃합니다. 멤버 타임아웃 권한을 요구합니다.", options=[
        discord.Option(discord.Member, name="사용자", description="타임아웃할 사용자", required=True),
        discord.Option(str, name="기간", description="타임아웃할 기간 (ex: 10초, 3분, 2시간, 1일, 4주)", required=False),
        discord.Option(str, name="사유", description="타임아웃할 사유 (선택)", required=False)])
    @discord.default_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, period: str, reason: str):
        if member == self.bot.user:
            return await ctx.send(":warning: 애플리케이션이 스스로를 타임아웃할 수 없습니다.", ephemeral=True)
        
        if period is None:
            return await ctx.respond(embed=discord.Embed(description=":warning: 타임아웃 기간을 입력해주세요. (ex: 10초, 3분, 2시간, 1일, 4주)"), ephemeral=True)
        
        match = re.match(r"(\d+)\s*(초|분|시간|일|주)", period)
        if not match:
            return await ctx.respond(embed=discord.Embed(description=":warning: 올바른 기간 형식이 아닙니다. (ex: 10초, 3분, 2시간, 1일, 4주)"), ephemeral=True)
        
        value = int(match.group(1))
        unit = match.group(2)
        timedelta = datetime.timedelta()

        if unit == "초": timedelta = datetime.timedelta(seconds=value)
        elif unit == "분": timedelta = datetime.timedelta(minutes=value)
        elif unit == "시간": timedelta = datetime.timedelta(hours=value)
        elif unit == "일": timedelta = datetime.timedelta(days=value)
        elif unit == "주": timedelta = datetime.timedelta(weeks=value)

        if timedelta > datetime.timedelta(days=28):
            return await ctx.respond(embed=discord.Embed(description=":warning: 타임아웃 기간은 28일(4주)보다 짧아야 합니다."), ephemeral=True)
        elif timedelta.total_seconds() <= 10:
            return await ctx.respond(embed=discord.Embed(description=":warning: 타임아웃 기간은 10초보다 길어야 합니다."), ephemeral=True)
        
        timeout_until = datetime.datetime.now(datetime.timezone.utc) + timedelta
        try:
            await member.timeout(timeout_until, reason=reason)
            embed = discord.Embed(title=f":no_entry: {member.display_name}님에게 타임아웃을 부여했습니다.", color=discord.Color.yellow())
            embed.add_field(name="지속 시간", value=period, inline=True)
            embed.add_field(name="사유", value=reason if reason else "사유 없음", inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.avatar)
            embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await ctx.respond(embed=embed)
            print(f"[Command | Moderate] 사용자를 타임아웃했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 타임아웃한 사용자: {member.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except discord.Forbidden:
            await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션에게 타임아웃 멤버 권한이 없거나 타임아웃할 사용자의 역할이 애플리케이션의 역할보다 높습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)

    @Timeout.command(name="해제", description="사용자의 타임아웃을 해제합니다. 멤버 타임아웃 권한을 요구합니다.", options=[
        discord.Option(discord.Member, name="사용자", description="타임아웃을 해제할 사용자", required=True),
        discord.Option(str, name="사유", description="타임아웃을 해제할 사유 (선택)", required=False)])
    @discord.default_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member, reason: str):
        try:
            await member.timeout(None, reason=reason)
            embed = discord.Embed(title=f":green_circle: {member.display_name}님의 타임아웃을 해제했습니다.", color=discord.Color.blue())
            embed.add_field(name="사유", value=reason if reason else "사유 없음", inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.avatar)
            embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await ctx.respond(embed=embed)
            print(f"[Command | Moderate] 사용자의 타임아웃을 해제했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.authorname}, 타임아웃을 해제한 사용자: {member.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except discord.errors.Forbidden:
            await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션에게 타임아웃 멤버 권한이 없거나 타임아웃을 해제할 사용자의 역할이 애플리케이션의 역할보다 높습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)

    Role = Moderate.create_subgroup("역할", "역할 부여/해제 명령어입니다.")

    @Role.command(name="부여", description="사용자에게 역할을 부여합니다. 역할 부여 권한을 요구합니다.", options=[
        discord.Option(discord.Member, name="사용자", description="역할을 해제할 사용자", required=True),
        discord.Option(discord.Role, name="역할", description="부여할 역할", required=True),
        discord.Option(str, name="사유", description="역할을 부여할 사유 (선택)", required=False)])
    @discord.default_permissions(manage_roles=True)
    async def role(self, ctx, member: discord.Member, role: discord.Role, *, reason: str = None):
        try:
            await member.add_roles(role, reason=reason)
            embed = discord.Embed(title=f":green_circle: {member.display_name}님에게 역할을 부여했습니다.", color=discord.Color.blue())
            embed.add_field(name="부여한 역할", value=role.mention, inline=True)
            embed.add_field(name="사유", value=reason if reason else "사유 없음", inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.avatar)
            embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await ctx.respond(embed=embed)
            print(f"[Command | Moderate] 사용자에게 역할을 부여했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 역할을 부여한 사용자: {member.name}, 역할: {role.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except discord.errors.Forbidden:
            await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션에게 역할 관리 권한이 없거나 부여할 사용자의 역할이 애플리케이션의 역할보다 높습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)

    
    @Role.command(name="해제", description="사용자의 역할을 해제합니다. 역할 부여 권한을 요구합니다.", options=[
        discord.Option(discord.Member, name="사용자", description="역할을 해제할 사용자", required=True),
        discord.Option(discord.Role, name="역할", description="부여할 역할", required=True),
        discord.Option(str, name="사유", description="역할을 부여하거나 해제할 사유 (선택)", required=False)])
    @discord.default_permissions(manage_roles=True)
    async def unrole(self, ctx, member: discord.Member, role: discord.Role, *, reason: str = None):
        try:
            await member.remove_roles(role, reason=reason)
            embed = discord.Embed(title=f":x: {member.display_name}님의 역할을 제거했습니다.", color=discord.Color.red())
            embed.add_field(name="제거된 역할", value=role.mention, inline=True)
            embed.add_field(name="사유", value=reason if reason else "사유 없음", inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.avatar)
            embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await ctx.respond(embed=embed)
            print(f"[Command | Moderate] 사용자의 역할을 제거했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 역할을 해제한 사용자: {member.name}, 역할: {role.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except discord.errors.Forbidden:
            await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션에게 역할 관리 권한이 없거나 해제할 사용자의 역할이 애플리케이션의 역할보다 높습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)

    Channel = Moderate.create_subgroup("채널", "채널 생성/삭제 명령어입니다.")

    @Channel.command(name="생성", description="서버에 채널을 생성합니다. 채널 관리 권한을 요구합니다.", options=[
        discord.Option(str, name="유형", description="채널 유형", choices=["텍스트", "음성", "카테고리"], required=True),
        discord.Option(str, name="이름", description="채널 이름", required=True),
        discord.Option(discord.CategoryChannel, name="카테고리", description="채널을 생성할 카테고리 (텍스트/음성 전용, 선택)", required=False)])
    @discord.default_permissions(manage_channels=True)
    async def create_channel(self, ctx: discord.ApplicationContext, type: str, name: str, category: discord.CategoryChannel = None):
        created_channel = None
        try:
            if type == "텍스트":
                if category:
                    created_channel = await ctx.guild.create_text_channel(name, category=category)
                else:
                    created_channel = await ctx.guild.create_text_channel(name)
                channel_type_display = ":keyboard: 텍스트"
            elif type == "음성":
                if category:
                    created_channel = await ctx.guild.create_voice_channel(name, category=category)
                else:
                    created_channel = await ctx.guild.create_voice_channel(name)
                channel_type_display = ":microphone: 음성"
            elif type == "카테고리":
                if category:
                    return await ctx.respond(embed=discord.Embed(description=":warning: 카테고리는 다른 카테고리에 속할 수 없어요."), ephemeral=True)
                created_channel = await ctx.guild.create_category(name)
                channel_type_display = ":keyboard::microphone: 카테고리"
            else:
                return await ctx.respond(embed=discord.Embed(description=":warning: 올바른 채널 유형을 선택하세요. (텍스트, 음성, 카테고리)"), ephemeral=True)
            
            if created_channel:
                embed = discord.Embed(title=":speech_balloon: 채널을 생성했습니다.", color=discord.Color.blue())
                embed.add_field(name="채널 이름", value=created_channel.name)
                embed.add_field(name="채널 유형", value=channel_type_display)
                if channel_type_display != "카테고리":
                    embed.add_field(name="채널 바로가기", value=created_channel.mention, inline=True)
                if category:
                    embed.add_field(name="상위 카테고리", value=category.name, inline=True)
                embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
                embed.set_footer(text=f"생성 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                await ctx.respond(embed=embed)
                print(f"[Commnad | Moderate] 채널을 생성했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
            else:
                await ctx.respond(embed=discord.Embed(description=":warning: 알 수 없는 오류가 발생했습니다. 애플리케이션 개발자에게 문의해주세요."), ephemeral=True)
        except discord.Forbidden:
            await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션에게 채널 관리 권한이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
    @create_channel.error
    async def create_channel_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.respond(embed=discord.Embed(description=":warning: 사용자에게 채널 관리 권한이 없습니다."), ephemeral=True)

    @Channel.command(name="삭제", description="서버의 채널 또는 카테고리를 삭제합니다. 채널 관리 권한을 요구합니다.", options=[
        discord.Option(discord.TextChannel, name="텍스트", description="삭제할 텍스트 채널을 선택하세요.", required=False),
        discord.Option(discord.VoiceChannel, name="음성", description="삭제할 음성 채널을 선택하세요.", required=False),
        discord.Option(discord.CategoryChannel, name="카테고리", description="삭제할 카테고리를 선택하세요.", required=False)])
    @discord.default_permissions(manage_channels=True)
    async def delete_channel(self, ctx: discord.ApplicationContext, text: discord.TextChannel = None, voice: discord.VoiceChannel = None, category: discord.CategoryChannel = None):
        selected_channel = [ch for ch in [text, voice, category] if ch is not None]
        if len(selected_channel) == 0:
            return await ctx.respond(embed=discord.Embed(description=":warning: 삭제할 채널을 하나 선택해주세요."), ephemeral=True)
        elif len(selected_channel) > 1:
            return await ctx.respond(embed=discord.Embed(description=":warning: 한 번에 하나의 채널만 삭제할 수 있습니다."), ephemeral=True)
        
        target_channel = selected_channel[0]

        try:
            channel_name_display = target_channel.name
            channel_id_display = target_channel.id
            await target_channel.delete()
            embed = discord.Embed(title=":x: 채널을 삭제했습니다.", color=discord.Color.red())
            embed.add_field(name="삭제된 채널 이름", value=channel_name_display, inline=True)
            embed.add_field(name="삭제된 채널 ID", value=channel_id_display, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_footer(text=f"생성 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await ctx.respond(embed=embed)
            print(f"[Command | Moderate] 채널을 삭제했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except discord.Forbidden:
            await ctx.send(embed=discord.Embed(description=":warning: 애플리케이션에게 채널 관리 권한이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
    @delete_channel.error
    async def delete_channel_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.respond(embed=discord.Embed(description=":warning: 사용자에게 채널 관리 권한이 없습니다."), ephemeral=True)

    Message = Moderate.create_subgroup("메세지", "메세지 삭제/보내기 명령어입니다.")

    @Message.command(name="삭제", description="메세지를 삭제합니다. 메세지 관리 권한을 요구합니다.", options=[
        discord.Option(int, name="개수", description="삭제할 메세지 개수", required=True)])
    @discord.default_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int):
        try:
            if amount < 1 or amount > 1000:
                return await ctx.respond(embed=discord.Embed(description=":warning: 1에서 1000 사이 정수를 입력해주세요."), ephemeral=True)
            await ctx.respond(f"**[알림]** {amount}개의 메시지를 삭제합니다.", ephemeral=True)
            await ctx.channel.purge(limit=amount)
            deleted_amount = await ctx.channel.purge(limit=amount)
            await ctx.send(f"**[알림]** {len(deleted_amount)}개의 메시지를 삭제했습니다. 이 메세지는 3초 후에 삭제됩니다.", delete_after=3)
            print(f"[Command | Moderate] 메세지를 삭제했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 갯수: {amount}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except discord.errors.Forbidden:
            await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션에게 메세지 관리 권한이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
    @clear.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.respond(embed=discord.Embed(description=":warning: 사용자에게 메세지 관리 권한이 없습니다."), ephemeral=True)

    @Message.command(name="보내기", description="사용자의 메세지를 전송합니다. 메세지 관리 권한을 요구합니다.", options=[
        discord.Option(str, name="메세지", description="전송할 메세지를 입력하세요.", required=True)])
    @discord.default_permissions(manage_messages=True)
    async def echo(self, ctx, *, message: str):
        mention_pattern = r"<@[!&]?\d+>|@everyone|@here"
        if re.search(mention_pattern, message):
            await ctx.respond(embed=discord.Embed(description=":warning: 멘션이 감지되어 메세지를 전송하지 않습니다. 멘션은 전송할 수 없습니다."), ephemeral=True)
        else:
            await ctx.respond(message)
            print(f"[Command | Moderate] 메세지 보내기 기능을 사용했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 메세지: {message}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    @echo.error
    async def echo_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.respond(embed=discord.Embed(description=":warning: 사용자에게 메세지 관리 권한이 없습니다."), ephemeral=True)

def setup(bot):
    bot.add_cog(moderate(bot))