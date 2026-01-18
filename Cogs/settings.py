import discord
import datetime
import os
import json
from discord.ext import commands
from discord.ui import View, Button

class settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.threshold_file = "server_threshold.json"
        self.threshold = {}
        self.settings_file = "server_settings.json"
        self.settings = self.load_settings()
        self.user_messages = {}
        self.punishment_logs = {}
        
    @commands.Cog.listener()
    async def on_ready(self):
        self.threshold = self.load_threshold()
        for guild_id, data in self.settings.items():
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    continue
                channel = guild.get_channel(data["captcha_channel"])
                if not channel:
                    continue
                role = guild.get_role(data["verify_role"])
                if not role:
                    continue
                captcha_mode = data.get("captcha_mode", "button")
                if captcha_mode == "button":
                    view = self.ButtonCaptchaView(role)
                    self.bot.add_view(view)
                else:
                    continue
            except discord.NotFound:
                continue
        print("[Settings] 서버 별 설정 파일 및 인증 파일을 로드했습니다.")

    def load_threshold(self):
        try:
            with open(self.threshold_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        
    def save_threshold(self):
        with open(self.threshold_file, "w") as f:
            json.dump(self.threshold, f, indent=4)

    def load_settings(self):
        if not os.path.exists(self.settings_file):
            return {}
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def save_settings(self):
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=4)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        guild_id = str(message.guild.id)
        user_id = str(message.author.id)

        if guild_id not in self.settings:
            return
        config = self.settings[guild_id]

        if not config.get("antispam_enabled", False):
            return

        now = datetime.datetime.utcnow()

        if guild_id not in self.user_messages:
            self.user_messages[guild_id] = {}
        if user_id not in self.user_messages[guild_id]:
            self.user_messages[guild_id][user_id] = []

        self.user_messages[guild_id][user_id].append(now)

        time_window = config.get("time_window", 5)
        threshold = config.get("spam_threshold", 5)
        timeout_duration_str = config.get("timeout_duration", "10초")
        timeout_seconds = self.parse_duration(timeout_duration_str)

        self.user_messages[guild_id][user_id] = [
            t for t in self.user_messages[guild_id][user_id]
            if (now - t).total_seconds() <= time_window
        ]

        if len(self.user_messages[guild_id][user_id]) >= threshold:
            try:
                timeout_until = datetime.datetime.utcnow() + datetime.timedelta(seconds=timeout_seconds)
                await message.author.timeout(timeout_until, reason="도배 감지")
                embed = discord.Embed(title=f":no_entry: {message.author.display_name}님에게 타임아웃을 부여했습니다.", color=discord.Color.yellow())
                embed.add_field(name="지속 시간", value=timeout_duration_str, inline=True)
                embed.add_field(name="사유", value="도배 감지", inline=True)
                embed.add_field(name="요청자", value="서버 소유자가 설정함", inline=True)
                embed.set_thumbnail(url=message.author.avatar)
                embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                await message.channel.send(embed=embed)
            except discord.Forbidden:
                await message.channel.send(embed=discord.Embed(description=f":warning: 애플리케이션에게 타임아웃 멤버 권한이 없습니다. 서버 소유자 또는 관리자에게 문의하세요."), ephemeral=True)

            self.user_messages[guild_id][user_id] = []

    def parse_duration(self, duration_str: str) -> datetime.timedelta:
        if "초" in duration_str:
            return datetime.timedelta(seconds=int(duration_str.replace("초","")))
        elif "분" in duration_str:
            return datetime.timedelta(minutes=int(duration_str.replace("분","")))
        elif "시간" in duration_str:
            return datetime.timedelta(hours=int(duration_str.replace("시간","")))
        elif "일" in duration_str:
            return datetime.timedelta(days=int(duration_str.replace("일","")))
        elif "주" in duration_str:
            return datetime.timedelta(weeks=int(duration_str.replace("주","")))
        else:
            return 10
        
    class ButtonCaptchaView(View):
        def __init__(self, role):
            super().__init__(timeout=None)
            self.role = role

        @discord.ui.button(label="인증하기", style=discord.ButtonStyle.green, custom_id="persistent_verify_button")
        async def verify(self, button: Button, interaction: discord.Interaction):
            member = interaction.user
            if self.role not in member.roles:
                await member.add_roles(self.role)
                await interaction.response.send_message(embed=discord.Embed(description=":white_check_mark: 역할을 부여했습니다."), ephemeral=True)
            else:
                await interaction.response.send_message(embed=discord.Embed(description=":white_check_mark: 이미 인증된 상태입니다."), ephemeral=True)

    Settings = discord.SlashCommandGroup("설정")
    Warning = Settings.create_subgroup("경고")

    @Warning.command(name="자동차단", description="지정한 경고 횟수 도달 시 멤버를 자동으로 차단합니다. 서버 소유자 권한을 요구합니다.", options=[
        discord.Option(str, name="상태", description="활성화 여부", choices=["활성화", "비활성화"], required=True),
        discord.Option(int, name="횟수", description="차단할 경고 횟수", required=False)])
    @discord.default_permissions(administrator=True)
    async def warn_threshold(self, ctx, enable: str, threshold: int = None):
        if not ctx.author == ctx.guild.owner:
            return await ctx.respond(embed=discord.Embed(description=":warning: 사용자가 서버 소유자가 아닙니다."), ephemeral=True)
        
        if enable == "활성화":
            if threshold is None:
                return await ctx.respond(embed=discord.Embed(description=":warning: 개수를 지정하세요."), ephemeral=True)
            if threshold <= 0:
                return await ctx.respond(embed=discord.Embed(description=":warning: 1 이상의 정수를 입력하세요."), ephemeral=True)

            guild_id_str = str(ctx.guild.id)
            self.threshold[guild_id_str] = {
                'enabled': True,
                'threshold': threshold}
            await ctx.respond(embed=discord.Embed(description=f":white_check_mark: 경고 `{threshold}`회 도달 시 사용자가 차단되도록 설정했습니다."), ephemeral=True)
            print(f"[Command | Settings] 사용자가 최대 경고 수를 변경했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
            
        if enable == "비활성화":
            if threshold is None:
                return await ctx.respond(embed=discord.Embed(description=":warning: 개수를 지정하세요."), ephemeral=True)
            if threshold <= 0:
                return await ctx.respond(embed=discord.Embed(description=":warning: 1 이상의 정수를 입력하세요."), ephemeral=True)

            guild_id_str = str(ctx.guild.id)
            self.threshold[guild_id_str] = {
                'enabled': False,
                'threshold': 0}
            await ctx.respond(embed=discord.Embed(description=f":white_check_mark: 자동 차단 기능을 비활성화했습니다."), ephemeral=True)
            print(f"[Command | Settings] 사용자가 자동 차단을 비활성화했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        self.save_threshold()
    @warn_threshold.error
    async def warn_threshold_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.respond(embed=discord.Embed(description=":warning: 최대 경고 값은 숫자여야 합니다."), ephemeral=True)

    @Settings.command(name="도배감지", description="서버의 도배 감지 기준을 설정합니다. 서버 소유자 권한을 요구합니다.", options=[
        discord.Option(str, name="상태", description="활성화 여부", choices=["활성화", "비활성화"], required=True),
        discord.Option(int, name="갯수", description="감지할 메세지 갯수", required=False),
        discord.Option(int, name="감지시간", description="지정한 시간 안에 메세지 갯수만큼 입력 시 타임아웃 (초 단위)", required=False),
        discord.Option(str, name="기간", description="타임아웃할 기간 (ex: 10초, 3분, 2시간, 1일, 4주)", required=False)])
    @discord.default_permissions(administrator=True)
    async def set_spam(self, ctx, mode: str, time: int, second: int, duration: str):
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.respond(embed=discord.Embed(description=":warning: 사용자가 서버 소유자가 아닙니다."), ephemeral=True)
        if mode == "활성화":
            if second is None:
                return await ctx.respond(embed=discord.Embed(description=":warning: 감지 시간을 지정하세요."), ephemeral=True)
            if time is None:
                return await ctx.respond(embed=discord.Embed(description=":warning: 감지할 메세지 갯수를 지정하세요."), ephemeral=True)
            if duration is None:
                return await ctx.respond(embed=discord.Embed(description=":warning: 타임아웃 기간을 지정하세요."), ephemeral=True)
            if second < 1:
                return await ctx.respond(embed=discord.Embed(description=":warning: 감지 시간은 1초보다 길어야 합니다."), ephemeral=True)
            if time < 1:
                return await ctx.respond(embed=discord.Embed(description=":warning: 감지할 메세지 갯수는 1 이상이어야 합니다."), ephemeral=True)
            if self.parse_duration(duration) > datetime.timedelta(days=28):
                return await ctx.respond(embed=discord.Embed(description=":warning: 타임아웃 기간은 28일(4주)보다 짧아야 합니다."), ephemeral=True)
            if self.parse_duration(duration) < datetime.timedelta(seconds=10):
                return await ctx.respond(embed=discord.Embed(description=":warning: 타임아웃 기간은 10초보다 길어야 합니다."), ephemeral=True)
            
            guild_id = str(ctx.guild.id)
            self.settings[guild_id] = {
                "antispam_enabled": True if mode == "활성화" else False,
                "spam_threshold": time,
                "time_window": second,
                "timeout_duration": duration 
            }
            self.save_settings()
            await ctx.respond(embed=discord.Embed(description=f":white_check_mark: `{second}초` 안에 메세지 `{time}`개 전송 시 `{duration}`동안 타임아웃하도록 설정했습니다."), ephemeral=True)
        elif mode == "비활성화":
            guild_id = str(ctx.guild.id)
            self.settings[guild_id] = {"antispam_enabled": False}
            self.save_settings()
            await ctx.respond(embed=discord.Embed(description=f":white_check_mark: 도배 감지 기능을 비활성화했습니다."), ephemeral=True)

    @Settings.command(name="인증", description="인증 메시지를 생성합니다. 서버 소유자 권한을 요구합니다.", options=[
        discord.Option(discord.Role, name="역할", description="인증 시 부여할 역할", default_member_permissions=discord.Permissions(administrator=True), required=True),
        discord.Option(str, name="메세지", description="인증 메세지 (선택)", required=False)])
    @discord.default_permissions(administrator=True)
    async def set_captcha(self, ctx, role: discord.Role, message: str = None):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.respond(embed=discord.Embed(description=":warning: 사용자에게 관리자 권한이 없습니다."), ephemeral=True)

        guild_id = str(ctx.guild.id)
        self.settings[guild_id] = {
            "captcha_channel": ctx.channel.id,
            "verify_role": role.id,
            "captcha_message": message if message else "✅ 인증하기 버튼을 클릭하여 인증하세요.",
            "captcha_message_id": None
        }
        self.save_settings()

        channel = ctx.channel
        sent_message = await channel.send(content=self.settings[guild_id]["captcha_message"], view=self.ButtonCaptchaView(role))
        self.settings[guild_id]["captcha_message_id"] = sent_message.id
        self.save_settings()

        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 인증 메세지를 생성했습니다."), ephemeral=True)

def setup(bot):
    bot.add_cog(settings(bot))