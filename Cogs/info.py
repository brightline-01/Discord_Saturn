import discord
import datetime
import psutil
from discord.ext import commands

class info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    Info = discord.SlashCommandGroup("정보")

    @Info.command(name="사용자", description="사용자의 정보를 표시합니다.", options=[discord.Option(discord.Member, name="사용자", description="정보를 표시할 사용자 (선택)", required=False)])
    async def user(self, ctx, member: discord.Member = None):
        if member is None:
            member = ctx.author
        roles = [role.name for role in member.roles if role.name != "@everyone"]
        embed = discord.Embed(title=f":bust_in_silhouette: {member.display_name}님의 사용자 정보", color=discord.Color.blue())
        embed.add_field(name="사용자명", value=member.name, inline=True)
        embed.add_field(name="별명", value=member.display_name, inline=True)
        embed.add_field(name="사용자 ID", value=member.id, inline=True)
        embed.add_field(name="계정 생성일", value=member.created_at.strftime("%Y년 %m월 %d일 %H:%M:%S"), inline=True)
        embed.add_field(name="서버 가입일", value=member.joined_at.strftime("%Y년 %m월 %d일 %H:%M:%S"), inline=True)
        embed.add_field(name="서버 역할", value=", ".join(roles) if roles else "역할 없음", inline=True)
        embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        embed.set_thumbnail(url=member.avatar)
        await ctx.respond(embed=embed)
        print(f"[Command | Info] 사용자 정보를 요청했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    @Info.command(name="서버", description="현재 서버의 정보를 표시합니다.")
    async def server(self, ctx):
        users = sum(1 for member in ctx.guild.members if not member.bot)
        apps = sum(1 for member in ctx.guild.members if member.bot)
        online = len([member for member in ctx.guild.members if member.status != discord.Status.offline])
        text = len(ctx.guild.text_channels)
        voice = len(ctx.guild.voice_channels)
        category = len(ctx.guild.categories)
        total = text + voice + category

        embed = discord.Embed(title=f":speech_balloon: {ctx.guild.name}의 서버 정보", color=discord.Color.blue())
        embed.add_field(name="서버 이름", value=ctx.guild.name, inline=True)
        embed.add_field(name="서버 설명", value=ctx.guild.description if ctx.guild.description else "지정되지 않음", inline=True)
        embed.add_field(name="서버 ID", value=ctx.guild.id, inline=True)
        embed.add_field(name="서버 소유자", value=f"{ctx.guild.owner.display_name} ({ctx.guild.owner.name})", inline=True)
        embed.add_field(name="서버 멤버 수", value=f"사용자 {users}명, 앱 {apps}명, 온라인 {online}명, 총 {ctx.guild.member_count}명", inline=True)
        embed.add_field(name="서버 생성일", value=discord.utils.format_dt(ctx.guild.created_at, "F"), inline=True)
        embed.add_field(name="서버 채널 수", value=f"텍스트 {text}개, 음성 {voice}개, 카테고리 {category}개, 총 {total}개", inline=True)
        embed.add_field(name="서버 역할 수", value=f"{len(ctx.guild.roles)}개", inline=True)
        if ctx.guild.premium_subscription_count > 0:
            embed.add_field(name="부스트 레벨", value=f"{ctx.guild.premium_tier}레벨, 부스트 {ctx.guild.premium_subscription_count}개", inline=True)
        else:
            embed.add_field(name="부스트 레벨", value="부스트 없음", inline=True)
        embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        embed.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.respond(embed=embed)
        print(f"[Command | Info] 서버 정보를 요청했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    
    @Info.command(name="앱", description="애플리케이션의 정보를 표시합니다.")
    async def info(self, ctx):
        virtual_memory = psutil.virtual_memory()
        disk_usage = psutil.disk_usage('/')
        embed = discord.Embed(title="애플리케이션의 정보를 표시합니다.", description="Saturn을 사용해주셔서 감사합니다.", color=discord.Color.blue())
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="앱 개발자", value="세린 (.__serin__.)", inline=True)
        embed.add_field(name="앱 이름", value="Saturn", inline=True)
        embed.add_field(name="앱 버전", value="1.1", inline=True)
        embed.add_field(name="서버 CPU 사용률", value=f"{psutil.cpu_percent(interval=1)}%", inline=True)
        embed.add_field(name="서버 메모리", value=f"{virtual_memory.total / (1024**3):.2f} GB", inline=True)
        embed.add_field(name="서버 메모리 사용률", value=f"{virtual_memory.percent}%", inline=True)
        embed.add_field(name="서버 디스크", value=f"{disk_usage.total / (1024**3):.2f} GB", inline=True)
        embed.add_field(name="서버 디스크 사용률", value=f"{disk_usage.percent}%", inline=True)
        embed.add_field(name="Python 버전", value="3.13.9", inline=True)
        embed.add_field(name="사용 중인 모듈", value="py-cord, asyncio, yt-dlp, json, os, psutil, googletrans, timedelta", inline=False)
        embed.add_field(name="서버 CPU", value="11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz", inline=False)
        embed.add_field(name="서버 OS", value="Microsoft Windows 11 Pro (10.0.26200.6584)", inline=False)
        embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.respond(embed=embed)
        print(f"[Command | Info] 애플리케이션 정보를 요청했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        
def setup(bot):
    bot.add_cog(info(bot))