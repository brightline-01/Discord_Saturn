import discord
import datetime
import json
from discord.ext import commands
from discord.ui import View, Button

class ConfirmResetView(View):
    def __init__(self, bot, ctx):
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.confirmed = False

    @discord.ui.button(label=":white_check_mark: 초기화", style=discord.ButtonStyle.danger)
    async def confirm(self, button: Button, interaction):
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(content=":white_check_mark: 경고 목록을 초기화했습니다.", view=None)

    @discord.ui.button(label=":x: 취소", style=discord.ButtonStyle.secondary)
    async def cancel(self, button: Button, interaction):
        self.stop()
        await interaction.response.edit_message(content=":x: 경고 목록 초기화를 취소했습니다.", view=None)

class warning(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.warning_file = "warning.json"
        self.warning_list = {}
        self.threshold_file = "server_threshold.json"
        self.threshold = {}
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.warning_list = self.load_warning()
        self.threshold = self.load_threshold()
        print("[Warning] 서버 별 경고 파일을 로드했습니다.")

    def load_threshold(self):
        try:
            with open(self.threshold_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def load_warning(self):
        try:
            with open(self.warning_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_warning(self):
        with open(self.warning_file, "w") as f:
            json.dump(self.warning_list, f, indent=4)

    Warning = discord.SlashCommandGroup("경고")

    @Warning.command(name="부여", description="사용자에게 경고를 부여합니다. 사용자 추방 권한을 요구합니다.", options=[
        discord.Option(discord.Member, name="사용자", description="경고를 부여할 사용자", required=True),
        discord.Option(int, name="개수", description="부여할 개수", required=True),
        discord.Option(str, name="사유", description="경고를 부여할 사유 (선택)", required=False)])
    @discord.default_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, count: int = 1, *, reason: str):
        if count <= 0:
            return await ctx.respond(embed=discord.Embed(description=":warning: 1 이상의 정수를 입력해야 합니다."), ephemeral=True)

        guild_id_str = str(ctx.guild.id)
        user_id_str = str(member.id)
        if guild_id_str not in self.warning_list:
            self.warning_list[guild_id_str] = {}

        if user_id_str not in self.warning_list[guild_id_str]:
            self.warning_list[guild_id_str][user_id_str] = {"count": 0, "reasons": []}

        self.warning_list[guild_id_str][user_id_str]["count"] += count
        for _ in range(count):
            self.warning_list[guild_id_str][user_id_str]["reasons"].append(reason if reason else "사유 없음")

        warning_count = self.warning_list[guild_id_str][user_id_str]["count"]
        self.save_warning()
        embed = discord.Embed(title=f":warning: {member.display_name}님에게 경고를 부여했습니다.", color=discord.Color.orange())
        embed.add_field(name="현재 경고 수", value=warning_count, inline=True)
        embed.add_field(name="사유", value=reason if reason else "사유 없음", inline=True)
        embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
        embed.set_thumbnail(url=member.avatar)
        embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.respond(embed=embed)
        print(f"[Command | Warning] 사용자가 사용자에게 경고를 부여했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 경고를 부여한 사용자: {member.name}, 부여한 경고 수: {warning_count}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

        guild_threshold = self.threshold.get(guild_id_str, None)
        kick_threshold = guild_threshold.get('threshold', 0) if guild_threshold else 0
        if kick_threshold <= 0:
            return
        
        if warning_count >= kick_threshold:
            try:
                await member.ban(reason=f"경고 {warning_count}회 도달 (기준 {kick_threshold}회)")
                await ctx.send(embed=discord.Embed(description=f":white_check_mark: {member.display_name}님을 경고 {kick_threshold}회 도달으로 차단했습니다."))
            except discord.Forbidden:
                await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션에게 멤버 추방 권한이 없거나 경고를 부여할 사용자의 역할이 애플리케이션의 역할보다 높습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
    @warn.error
    async def warn_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.respond(embed=discord.Embed(description=":warning: 사용자에게 멤버 추방 권한이 없습니다."), ephemeral=True)

    @Warning.command(name="삭제", description="사용자의 경고를 삭제합니다. 사용자 추방 권한을 요구합니다.", options=[
        discord.Option(discord.Member, name="사용자", description="경고를 삭제할 사용자", required=True),
        discord.Option(int, name="개수", description="삭제할 개수", required=True)])
    @discord.default_permissions(kick_members=True)
    async def unwarn(self, ctx, member: discord.Member, count: int = 1):
        guild_id_str = str(ctx.guild.id)
        user_id_str = str(member.id)
        warnings = self.warning_list.get(guild_id_str, {}).get(user_id_str)
        if not warnings or warnings.get("count", 0) <= 0:
            return await ctx.respond(embed=discord.Embed(description=f":white_check_mark: {member.display_name}님이 받은 경고가 없습니다."), ephemeral=True)
        
        if count <= 0:
            return await ctx.respond(embed=discord.Embed(description=":warning: 1 이상의 정수를 입력하세요."), ephemeral=True)
    
        if count > warnings.get("count", 0):
            count = warnings.get("count", 0)

        for _ in range(count):
            warnings["reasons"].pop(0)

        warnings["count"] = len(warnings.get("reasons", []))
        if warnings["count"] <= 0:
            del self.warning_list[guild_id_str][user_id_str]
            
        if guild_id_str in self.warning_list and not self.warning_list[guild_id_str]:
            del self.warning_list[guild_id_str]

        self.save_warning()
        warning_count = self.warning_list.get(guild_id_str, {}).get(user_id_str, {}).get("count", 0)
        embed = discord.Embed(title=f":green_circle: {member.display_name}님의 경고를 삭제했습니다.", color=discord.Color.blue())
        embed.add_field(name="현재 경고 갯수", value=warning_count, inline=True)
        embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
        embed.set_thumbnail(url=member.avatar)
        embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.respond(embed=embed)
        print(f"[Command | Warning] 사용자가 사용자의 경고를 삭제했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 경고를 삭제한 사용자: {member.name}, 삭제한 경고 수: {count}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    @unwarn.error
    async def unwarn_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.respond(embed=discord.Embed(description=":warning: 사용자에게 멤버 추방 권한이 없습니다."), ephemeral=True)

    @Warning.command(name="목록", description="사용자의 경고 목록을 표시합니다.", options=[
        discord.Option(discord.Member, name="사용자", description="경고 목록을 표시할 사용자 (선택)", required=False)])
    @discord.default_permissions()
    async def warnings(self, ctx, member: discord.Member = None):
        if member is None:
            member = ctx.author

        guild_id_str = str(ctx.guild.id)
        user_id_str = str(member.id)
        warnings = self.warning_list.get(guild_id_str, {}).get(user_id_str)
        if not warnings:
            return await ctx.respond(embed=discord.Embed(description=":white_check_mark: {member.display_name}님이 받은 경고가 없습니다."), ephemeral=True)
        
        warning_count = warnings.get("count", 0)
        reasons_list = warnings.get("reasons", [])
        if reasons_list:
            reasons_text = "\n".join([f"{i+1}. {reason}" for i, reason in enumerate(reasons_list)])
        else:
            reasons_text = "사유 없음"

        embed = discord.Embed(title=f":warning: {member.display_name} 님의 경고 목록", color=discord.Color.yellow())
        embed.add_field(name="전체 경고 횟수", value=warning_count, inline=False)
        embed.add_field(name="경고 사유", value=reasons_text, inline=False)
        embed.set_thumbnail(url=member.avatar)
        await ctx.respond(embed=embed)
        print(f"[Command | Warning] 사용자가 사용자의 경고 기록을 요청했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 대상: {member.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    @Warning.command(name="전체삭제", description="서버 내 모든 사용자의 경고를 초기화합니다. 서버 소유자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def reset_warnings(self, ctx):
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.respond(embed=discord.Embed(description=":warning: 사용자가 서버 소유자가 아닙니다."), ephemeral=True)
    
        view = ConfirmResetView(self.bot, ctx)
        await ctx.respond(embed=discord.Embed(description=":warning: 되돌릴 수 없습니다. 진행하시겠습니까?"), view=view, ephemeral=True)

        await view.wait()
        if view.confirmed:
            guild_id_str = str(ctx.guild.id)
            self.warning_list[guild_id_str] = {}
            self.save_warning()
            await ctx.send(":white_check_mark: 서버 내 모든 사용자의 경고를 초기화했습니다.")
            print(f"[Command | Warning] 사용자가 서버 경고를 초기화했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

def setup(bot):
    bot.add_cog(warning(bot))