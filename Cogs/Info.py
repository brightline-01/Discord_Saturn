import discord, platform, psutil, winreg
from Config import APP_NAME, APP_VER, APP_DEV
from Resources import Current_Time, Print_Log
from discord.ext import commands

class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    Info_CMDGroup = discord.SlashCommandGroup("정보")

    # /정보 사용자 [@사용자]
    @Info_CMDGroup.command(name="사용자", description="사용자의 정보를 표시합니다.")
    async def Info_Member(self, ctx, Member: discord.Option(discord.User, name="사용자", description="정보를 표시할 사용자 (선택)", required=False) = None):
        if Member is None:   # 멤버가 None인 경우
            Member = ctx.author   # 멤버를 명령어 사용자로 지정

        # 현재 서버의 Member 객체 가져오기 (없으면 None)
        Guild_Member = ctx.guild.get_member(Member.id)

        if Guild_Member:
            Display_Name = discord.utils.escape_markdown(f"{Guild_Member.display_name} (앱)" if Guild_Member.bot else Guild_Member.display_name)
            Joined_At = Guild_Member.joined_at.strftime("%Y년 %m월 %d일 %H:%M:%S")
            Role_List = [role.mention for role in reversed(Guild_Member.roles) if role.name != "@everyone"]
        else:
            Display_Name = discord.utils.escape_markdown(f"{Member.display_name} (앱)" if Member.bot else Member.display_name)
            Joined_At = "이 서버에 속하지 않음"
            Role_List = []

        # Embed 생성
        embed = discord.Embed(title=f"👤 {Display_Name}님의 사용자 정보", color=discord.Color.blue())
        embed.add_field(name="사용자명", value=discord.utils.escape_markdown(Member.name), inline=True)
        embed.add_field(name="별명", value=discord.utils.escape_markdown(Member.display_name), inline=True)
        embed.add_field(name="사용자 ID", value=Member.id, inline=True)
        embed.add_field(name="계정 생성일", value=Member.created_at.strftime("%Y년 %m월 %d일 %H:%M:%S"), inline=True)
        embed.add_field(name="서버 가입일", value=Joined_At, inline=True)
        embed.add_field(name="서버 역할", value=", ".join(Role_List[:20]) if Role_List else "역할 없음", inline=True)
        embed.add_field(name="애플리케이션 여부", value="예" if Member.bot else "아니요", inline=True)
        embed.set_footer(text=f"일시: {Current_Time()}")
        embed.set_thumbnail(url=Member.display_avatar.url)
        
        await ctx.respond(embed=embed)   # Embed 전송
        Print_Log("Info", "사용자 정보를 표시했습니다.", ctx.guild.name, ctx.author.name, Member.name)   # 로그 출력

    # /정보 서버
    @Info_CMDGroup.command(name="서버", description="현재 서버의 정보를 표시합니다.")
    async def Info_Server(self, ctx):
        # 서버 통계 생성
        Users = sum(1 for member in ctx.guild.members if not member.bot)
        Apps = sum(1 for member in ctx.guild.members if member.bot)
        Online = len([member for member in ctx.guild.members if member.status != discord.Status.offline])
        Text_Channels = len(ctx.guild.text_channels)
        Voice_Channels = len(ctx.guild.voice_channels)
        Categories = len(ctx.guild.categories)
        Total = Text_Channels + Voice_Channels + Categories
        Boost_Info = (f"{ctx.guild.premium_tier}레벨, 부스트 {ctx.guild.premium_subscription_count}개"
        if ctx.guild.premium_subscription_count > 0 else "부스트 없음")

        # Embed 생성
        embed = discord.Embed(title=f"💬 {ctx.guild.name}의 서버 정보", color=discord.Color.blue())
        embed.add_field(name="서버 이름", value=ctx.guild.name, inline=True)
        embed.add_field(name="서버 설명", value=ctx.guild.description if ctx.guild.description else "설명 없음", inline=True)
        embed.add_field(name="서버 ID", value=ctx.guild.id, inline=True)
        embed.add_field(name="서버 소유자", value=f"{ctx.guild.owner.display_name} ({ctx.guild.owner.name})", inline=True)
        embed.add_field(name="서버 생성일", value=ctx.guild.created_at.strftime("%Y년 %m월 %d일 %H:%M:%S"), inline=True)
        embed.add_field(name="서버 멤버 수", value=f"사용자 {Users}명, 앱 {Apps}명, 온라인 {Online}명, 총 {ctx.guild.member_count}명", inline=True)
        embed.add_field(name="서버 채널 수", value=f"텍스트 {Text_Channels}개, 음성 {Voice_Channels}개, 카테고리 {Categories}개, 총 {Total}개", inline=True)
        embed.add_field(name="서버 역할 수", value=f"{len(ctx.guild.roles)}개", inline=True)
        embed.add_field(name="서버 이모지 수", value=f"{len(ctx.guild.emojis)}개", inline=True)
        embed.add_field(name="부스트 정보", value=Boost_Info, inline=True)
        embed.set_footer(text=f"일시: {Current_Time()}")
        embed.set_thumbnail(url=ctx.guild.icon.url)

        await ctx.respond(embed=embed)   # Embed 전송
        Print_Log("Info", "서버 정보를 표시했습니다.", ctx.guild.name, ctx.author.name)   # 로그 출력

    # /정보 앱
    @Info_CMDGroup.command(name="앱", description="애플리케이션의 정보를 표시합니다.")
    async def Info_Application(self, ctx):
        # 서버 정보 생성
        RAM = psutil.virtual_memory()
        DISK = psutil.disk_usage('/')
        CPU_Name = winreg.QueryValueEx(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"),
        "ProcessorNameString")[0]

        def Format_Usage(Value):
            return f"{Value.used / 1024**3:.2f} GB / {Value.total / 1024**3:.2f} GB ({Value.percent}%)"
        
        # Embed 생성
        embed = discord.Embed(title="🤖 애플리케이션의 정보를 표시합니다.", description=f"{APP_NAME}을 사용해주셔서 감사합니다.", color=discord.Color.blue())
        embed.add_field(name="앱 개발자", value=discord.utils.escape_markdown(APP_DEV), inline=True)
        embed.add_field(name="앱 이름", value=discord.utils.escape_markdown(APP_NAME), inline=True)
        embed.add_field(name="앱 버전", value=APP_VER, inline=True)
        embed.add_field(name="서버 CPU 사용량", value=f"{psutil.cpu_percent(interval=1)}%", inline=True)
        embed.add_field(name="서버 메모리 사용량", value=Format_Usage(RAM), inline=True)
        embed.add_field(name="서버 디스크 사용량", value=Format_Usage(DISK), inline=True)
        embed.add_field(name="Python 버전", value=platform.python_version(), inline=True)
        embed.add_field(name="서버 CPU", value=CPU_Name, inline=True)
        embed.add_field(name="서버 OS", value=platform.platform(), inline=True)
        embed.set_footer(text=f"일시: {Current_Time()}")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        await ctx.respond(embed=embed)   # Embed 전송
        Print_Log("Info", "애플리케이션 정보를 표시했습니다.", ctx.guild.name, ctx.author.name)   # 로그 출력

def setup(bot):
    bot.add_cog(Info(bot))