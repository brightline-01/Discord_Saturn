import discord, datetime
from discord.ext import commands

class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    Info_CMDGroup = discord.SlashCommandGroup("정보")

    @Info_CMDGroup.command(name="사용자", description="사용자의 정보를 표시합니다.")
    async def Info_Member(self, ctx, member: discord.Option(discord.Member, name="사용자", description="정보를 표시할 사용자 (선택)", required=False) = None):
        if member is None:
            member = ctx.author
        Role_List = [role.name for role in member.roles if role.name != "@everyone"]
        Display_Name = f"{member.display_name} (앱)" if member.bot else member.display_name
        embed = discord.Embed(title=f":bust_in_silhouette: {Display_Name}님의 사용자 정보", color=discord.Color.blue())
        embed.add_field(name="사용자명", value=member.name, inline=True)
        embed.add_field(name="별명", value=member.display_name, inline=True)
        embed.add_field(name="사용자 ID", value=member.id, inline=True)
        embed.add_field(name="계정 생성일", value=member.created_at.strftime("%Y년 %m월 %d일 %H:%M:%S"), inline=True)
        embed.add_field(name="서버 가입일", value=member.joined_at.strftime("%Y년 %m월 %d일 %H:%M:%S"), inline=True)
        embed.add_field(name="서버 역할", value=", ".join(Role_List) if Role_List else "역할 없음", inline=True)
        embed.add_field(name="애플리케이션 여부", value="예" if member.bot else "아니요", inline=True)
        embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')}")
        embed.set_thumbnail(url=member.avatar)
        await ctx.respond(embed=embed)
        print(f"[Command | Info] 사용자 정보를 요청했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name})")

def setup(bot):
    bot.add_cog(Info(bot))