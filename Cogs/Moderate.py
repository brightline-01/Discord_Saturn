import discord
from Resources import Current_Time, Error_Dialog_Embed
from discord.ext import commands

class Moderate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    Moderate_CMDGroup = discord.SlashCommandGroup("관리")

    @Moderate_CMDGroup.command(name="추방", description="사용자를 서버에서 추방합니다. 멤버 추방 권한을 요구합니다.")
    @discord.default_permissions(kick_members=True)
    async def Kick_Member(self, ctx, member: discord.Option(discord.Member, name="사용자", description="추방할 사용자를 지정하세요."),
        reason: discord.Option(str, name="사유", description="추방할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.kick_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 추방 권한이 없습니다."), ephemeral=True)

        if member == ctx.author:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자가 스스로를 추방할 수 없습니다."), ephemeral=True)

        if member == self.bot.user:
            return await ctx.respond(embed=Error_Dialog_Embed("애플리케이션이 스스로를 추방할 수 없습니다."), ephemeral=True)

        # 추방 실행
        try:
            await member.kick(reason=reason)
            embed = discord.Embed(title=f"⚠️ {member.display_name}님을 서버에서 추방했습니다.", color=discord.Color.red())
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.avatar)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            print(f"[Moderate] 사용자를 추방했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 추방한 사용자: {member.name})")
        # 애플리케이션 권한 예외 처리
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 멤버를 추방할 권한이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)

    @Moderate_CMDGroup.command(name="차단", description="사용자를 서버에서 차단합니다. 서버 외부 사용자는 ID로 차단 가능합니다.")
    @discord.default_permissions(ban_members=True)
    async def Ban_Member(self, ctx,
        user: discord.Option(str, name="사용자", description="차단할 사용자의 멘션 또는 사용자 ID를 입력하세요."),
        reason: discord.Option(str, name="사유", description="차단할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        # 요청자 권한 확인
        if not ctx.author.guild_permissions.ban_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 차단 권한이 없습니다."), ephemeral=True)

        # 사용자 입력 값 처리
        User_ID_Match = re.search(r'\d+', user)
        if not User_ID_Match:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자를 찾을 수 없습니다. 올바른 사용자 멘션 또는 ID를 입력해주세요."), ephemeral=True)
        User_ID = int(User_ID_Match.group())

        # 차단 대상 처리
        Target_User = await self.bot.fetch_user(User_ID)

        # 권한 확인
        if Target_User.id == ctx.author.id:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자가 스스로를 차단할 수 없습니다."), ephemeral=True)

        if Target_User.bot:
            return await ctx.respond(embed=Error_Dialog_Embed("애플리케이션을 차단할 수 없습니다."), ephemeral=True)

        # 이미 차단된 사용자인지 확인
        try:
            await ctx.guild.fetch_ban(Target_User)
            return await ctx.respond(embed=Error_Dialog_Embed("이미 차단된 사용자입니다."), ephemeral=True)
        except discord.NotFound:
            pass

        # 차단 실행
        try:
            await ctx.guild.ban(Target_User, reason=reason)
            embed = discord.Embed(title=f"🔨 {Target_User.display_name}님을 서버에서 차단했습니다.", color=discord.Color.red())
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=Target_User.avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            print(f"[Moderate] 사용자를 차단했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 차단한 사용자: {Target_User.name})")
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 사용자를 차단할 권한이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)

def setup(bot):
    bot.add_cog(Moderate(bot))