import discord, os, json, datetime
from discord.ext import commands
from Resources import Current_Time, Error_Dialog_Embed, Success_Dialog_Embed, Print_Log, Load_Data, Save_Data, Parse_Duration, Button_Interaction

# 경고 전체 초기화 확인 뷰
class Reset_Confirm_View(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=30)
        self.Author = author
        self.Value = None

    @discord.ui.button(label="예, 진행합니다", style=discord.ButtonStyle.red)
    async def Confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        await Button_Interaction(self, interaction, True)

    @discord.ui.button(label="아니요", style=discord.ButtonStyle.green)
    async def Cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await Button_Interaction(self, interaction, False)

# 인증 버튼 뷰 클래스
class Verify_View(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="인증하기", style=discord.ButtonStyle.green, emoji="✅", custom_id="member_verify")
    async def Verify(self, button: discord.ui.Button, interaction: discord.Interaction):
        Settings = Load_Data("Datas/Settings_Data.json")
        Role_ID = Settings.get(str(interaction.guild.id), {}).get("Verify", {}).get("Role_ID")
        
        if not Role_ID:
            return await interaction.response.send_message(embed=Error_Dialog_Embed("이 서버에 설정된 인증 역할이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
        
        Role = interaction.guild.get_role(Role_ID)
        if not Role:
            return await interaction.response.send_message(embed=Error_Dialog_Embed("설정된 역할을 찾을 수 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
            
        if Role in interaction.user.roles:
            return await interaction.response.send_message(embed=Success_Dialog_Embed("이미 인증된 상태입니다."), ephemeral=True)
            
        try:
            await interaction.user.add_roles(Role, reason="멤버 인증")
            await interaction.response.send_message(embed=Success_Dialog_Embed(f"**{Role.name}** 역할을 부여했습니다."), ephemeral=True)
            Print_Log("Settings", "멤버를 인증했습니다.", interaction.guild.name, interaction.user.name)
        except Exception as e:
            await interaction.response.send_message(embed=Error_Dialog_Embed(f"역할을 부여하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.Warning_Data_Path = "Datas/Warning_Data.json"
        self.Settings_Data_Path = "Datas/Settings_Data.json"

    Settings_CMDGroup = discord.SlashCommandGroup("설정")
    Warning_Settings_CMDGroup = Settings_CMDGroup.create_subgroup("경고")

    # /설정 경고 초기화
    @Warning_Settings_CMDGroup.command(name="초기화", description="서버의 모든 경고 데이터를 초기화합니다. 서버 소유자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Reset_Warnings_Data(self, ctx):
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 서버 소유자 권한이 없습니다."), ephemeral=True)

        View = Reset_Confirm_View(ctx.author)
        Response = await ctx.respond(embed=discord.Embed(
            title="⚠️ 서버 경고 데이터 초기화",
            description="정말로 이 서버의 모든 경고 데이터를 초기화하시겠습니까? **이 작업은 되돌릴 수 없습니다.**",
            color=discord.Color.red()
        ), view=View, ephemeral=True)
        await View.wait()
        
        if View.Value is None:
            return await Response.edit(embed=Error_Dialog_Embed("시간이 초과되어 초기화가 취소되었습니다."), view=None)
            
        if not View.Value:
            return await Response.edit(embed=Success_Dialog_Embed("경고 데이터 초기화가 취소되었습니다."), view=None)
        
        try:
            Warnings = Load_Data(self.Warning_Data_Path)
            Guild_ID = f"{ctx.guild.id}_"
            Deleted = [key for key in Warnings.keys() if key.startswith(f"{Guild_ID}")]

            if not Deleted:
                return await Response.edit(embed=Error_Dialog_Embed("이 서버에 저장된 경고 데이터가 없습니다."), view=None)
            
            for key in Deleted:
                del Warnings[key]

            Save_Data(self.Warning_Data_Path, Warnings)
            await Response.edit(embed=Success_Dialog_Embed("이 서버의 모든 경고 데이터를 초기화했습니다."), view=None)
            Print_Log("Settings", "경고 데이터를 초기화했습니다.", ctx.guild.name, ctx.author.name)
        except Exception as e:
            await Response.edit(embed=Error_Dialog_Embed(f"경고 데이터 초기화 중 오류가 발생했습니다. ({e})"), view=None)

    # /설정 경고 자동처벌 [활성화 / 비활성화] [횟수] [처벌] [기간]
    @Warning_Settings_CMDGroup.command(name="자동처벌", description="일정 경고 횟수 도달 시 자동으로 부여할 처벌을 설정합니다. 서버 관리자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Setup_Warning_Threshold(self, ctx, Enabled: discord.Option(bool, name="활성화", description="자동 처벌 활성화 여부를 선택하세요."),
        Count: discord.Option(int, name="횟수", description="처벌을 실행할 경고 횟수를 지정하세요.", min_value=1),
        Action: discord.Option(str, name="처벌", description="자동으로 실행할 처벌의 종류를 선택하세요.", choices=["차단", "추방", "타임아웃"]),
        Duration: discord.Option(str, name="기간", description="타임아웃을 부여할 기간을 입력하세요. (ex: 7일, 10분)", required=False, default="7일")):
        
        # 권한 확인
        if not ctx.author.guild_permissions.administrator:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 서버 관리자 권한이 없습니다."), ephemeral=True)

        # 타임아웃 기간 형식 확인
        if Action == "타임아웃" and not Parse_Duration(Duration):
            return await ctx.respond(embed=Error_Dialog_Embed("올바른 기간 형식을 입력해주세요."), ephemeral=True)

        try:
            # 설정 불러오기
            Settings_Data = Load_Data(self.Settings_Data_Path)
            Guild_Settings = Settings_Data.setdefault(str(ctx.guild.id), {})
            
            if not Enabled:
                Guild_Settings.pop("Auto_Punish", None)
                Message = "자동 처벌 설정을 비활성화했습니다."
            else:
                Guild_Settings["Auto_Punish"] = {"Enabled": True, "Count": Count, "Action": Action, "Duration": Duration if Action == "타임아웃" else None}
                Message = f"경고 **{Count}회** 도달 시 자동으로 {Action}{f' ({Duration})' if Action == '타임아웃' else ''}하도록 설정했습니다."
            
            Save_Data(self.Settings_Data_Path, Settings_Data)
            await ctx.respond(embed=Success_Dialog_Embed(Message), ephemeral=True)
            Print_Log("Settings", "자동 처벌 설정을 변경했습니다.", ctx.guild.name, ctx.author.name, Extra=f"상태: {'활성화' if Enabled else '비활성화'}")
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"설정을 저장하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # 보안 시스템 설정 명령어 그룹
    Security_Settings_CMDGroup = Settings_CMDGroup.create_subgroup("보안")

    async def Update_Security_Settings(self, ctx, Key: str, Data: dict | None, Message: str, Log_Name: str, Enabled: bool):
        try:
            Settings_Data = Load_Data(self.Settings_Data_Path)
            Guild_Settings = Settings_Data.setdefault(str(ctx.guild.id), {})

            if Data is None:
                Guild_Settings.pop(Key, None)
            else:
                Guild_Settings[Key] = Data

            Save_Data(self.Settings_Data_Path, Settings_Data)
            await ctx.respond(embed=Success_Dialog_Embed(Message), ephemeral=True)
            Print_Log("Settings", Log_Name, ctx.guild.name, ctx.author.name, Extra=f"설정: {'활성화' if Enabled else '비활성화'}")
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"설정을 저장하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /설정 보안 도배감지 [활성화 / 비활성화] [개수] [시간] [처벌] [모드] [기간]
    @Security_Settings_CMDGroup.command(name="도배감지", description="도배 감지 시 자동으로 부여할 처벌을 설정합니다. 서버 관리자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Setup_Anti_Spam(self, ctx, Enabled: discord.Option(bool, name="활성화", description="도배 감지 활성화 여부를 선택하세요."),
        Count: discord.Option(int, name="개수", description="감지할 메시지 개수를 지정하세요. (2 ~)", min_value=2),
        Seconds: discord.Option(int, name="시간", description="메시지를 감지할 시간을 지정하세요. (초, 1 ~ 60)", min_value=1, max_value=60),
        Action: discord.Option(str, name="처벌", description="실행할 처벌의 종류를 지정하세요.", choices=["차단", "추방", "타임아웃"]),
        Mode: discord.Option(str, name="모드", description="감지할 메시지의 종류를 지정하세요.", choices=["모든 메세지", "동일한 메세지"]),
        Duration: discord.Option(str, name="기간", description="타임아웃을 부여할 기간을 지정하세요. (선택)", required=False, default="1시간")):
        # 권한 확인
        if not ctx.author.guild_permissions.administrator:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 서버 관리자 권한이 없습니다."), ephemeral=True)

        # 타임아웃 기간 형식 확인
        if Action == "타임아웃" and not Parse_Duration(Duration):
            return await ctx.respond(embed=Error_Dialog_Embed("올바른 기간 형식을 입력해주세요."), ephemeral=True)

        Data = None
        Message = "도배 감지 설정을 비활성화했습니다."

        if Enabled:
            Data = {
                "Enabled": True, "Count": Count, "Seconds": Seconds,
                "Action": Action, "Mode": Mode, "Duration": Duration if Action == "타임아웃" else None
            }
            Message = f"**{Seconds}초** 이내에 **{'모든' if Mode == '모든 메세지' else '동일한 내용의'}** 메시지를 **{Count}개** 이상 보낼 경우 자동으로 **{Action}**하도록 설정했습니다."

        await self.Update_Security_Settings(ctx, "Anti_Spam", Data, Message, "도배 감지 설정을 변경했습니다.", Enabled)

    # /설정 보안 권한부여감지 [활성화 / 비활성화]
    @Security_Settings_CMDGroup.command(name="권한부여감지", description="관리자 권한 부여 시 권한을 부여한 사용자와 대상자를 차단합니다. 서버 소유자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Setup_Anti_Admin(self, ctx, Enabled: discord.Option(bool, name="활성화", description="권한 부여 감지 활성화 여부를 선택하세요.")):
        # 권한 확인
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 서버 소유자 권한이 없습니다."), ephemeral=True)

        await self.Update_Security_Settings(ctx, "Anti_Admin", {"Enabled": Enabled}, "권한 부여 감지 설정을 변경했습니다.", Enabled)

    # /설정 보안 레이드감지 [활성화 / 비활성화] [개수] [시간]
    @Security_Settings_CMDGroup.command(name="레이드감지", description="지정한 시간 내 다발적 채널 생성 또는 삭제를 감지합니다. 서버 소유자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Setup_Anti_Raid(self, ctx, Enabled: discord.Option(bool, name="활성화", description="채널 방어 활성화 여부를 선택하세요."),
        Count: discord.Option(int, name="개수", description="감지할 채널 작업 개수를 지정하세요. (2 ~)", min_value=2),
        Seconds: discord.Option(int, name="시간", description="채널 작업을 감지할 시간을 지정하세요. (초, 1 ~ 60)", min_value=1, max_value=60)):
        
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 서버 소유자 권한이 없습니다."), ephemeral=True)

        Data = None
        Message = "레이드 감지 설정을 비활성화했습니다."

        if Enabled:
            Data = {"Enabled": True, "Count": Count, "Seconds": Seconds}
            Message = f"**{Seconds}초** 이내에 채널을 **{Count}개** 이상 생성 또는 삭제할 경우 사용자를 자동으로 **차단**하도록 설정했습니다."

        await self.Update_Security_Settings(ctx, "Anti_Channel", Data, Message, "레이드 감지 설정을 변경했습니다.", Enabled)

    # 티켓 시스템 설정 명령어 그룹
    Ticket_Settings_CMDGroup = Settings_CMDGroup.create_subgroup("티켓")

    # /설정 티켓 설정 [생성] [보관] [역할] [로그]
    @Ticket_Settings_CMDGroup.command(name="설정", description="이 서버의 티켓 시스템을 설정합니다. 관리자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Setup_Ticket_System(self, ctx, Category: discord.Option(discord.CategoryChannel, name="생성", description="티켓이 생성될 카테고리를 선택하세요.", required=True),
        Archive: discord.Option(discord.CategoryChannel, name="보관", description="티켓이 보관될 카테고리를 선택하세요.", required=True),
        Role: discord.Option(discord.Role, name="역할", description="티켓에 접근할 수 있는 관리자 역할을 선택하세요.", required=True),
        Log: discord.Option(discord.TextChannel, name="로그", description="티켓 대화 내역(txt)이 저장될 채널을 선택하세요. (선택)", required=False)):
        
        try:
            Settings_Data = Load_Data(self.Settings_Data_Path)
            Ticket_Settings = Settings_Data.setdefault(str(ctx.guild.id), {}).setdefault("Ticket", {})
            
            Ticket_Settings.update({
                "Category_ID": Category.id,
                "Archive_Category_ID": Archive.id,
                "Staff_Role_ID": Role.id,
                "Log_Channel_ID": Log.id if Log else None
            })
            
            Save_Data(self.Settings_Data_Path, Settings_Data)
            
            embed = discord.Embed(title="✅ 티켓 시스템을 설정했습니다.", color=discord.Color.green())
            if Category: embed.add_field(name="생성 카테고리", value=Category.mention, inline=True)
            if Archive: embed.add_field(name="보관 카테고리", value=Archive.mention, inline=True)
            if Role: embed.add_field(name="관리자 역할", value=Role.mention, inline=True)
            if Log: embed.add_field(name="로그 채널", value=Log.mention, inline=True)
            
            await ctx.respond(embed=embed, ephemeral=True)
            Print_Log("Settings", "티켓 시스템을 설정했습니다.", ctx.guild.name, ctx.author.name)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"설정을 저장하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /설정 티켓 초기화
    @Ticket_Settings_CMDGroup.command(name="초기화", description="이 서버의 티켓 시스템 설정을 초기화합니다. 서버 소유자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Reset_Ticket_System(self, ctx):
        # 권한 확인
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 서버 소유자 권한이 없습니다."), ephemeral=True)

        View = Reset_Confirm_View(ctx.author)

        Response = await ctx.respond(embed=discord.Embed(
            title="⚠️ 티켓 시스템 초기화",
            description="정말로 이 서버의 티켓 시스템 설정을 초기화하시겠습니까? **이 작업은 되돌릴 수 없습니다.**",
            color=discord.Color.red()
        ), view=View, ephemeral=True)
        await View.wait()
        
        if View.Value is None:
            return await Response.edit(embed=Error_Dialog_Embed("시간이 초과되었습니다."), view=None)

        if not View.Value:
            return await Response.edit(embed=Success_Dialog_Embed("티켓 시스템 설정 초기화를 취소했습니다."), view=None)

        try:
            Settings_Data = Load_Data(self.Settings_Data_Path)
            Guild_Settings = Settings_Data.get(str(ctx.guild.id), {})
            
            if "Ticket" not in Guild_Settings:
                return await Response.edit(embed=Error_Dialog_Embed("이 서버에 저장된 티켓 시스템 설정이 없습니다."), view=None)

            del Guild_Settings["Ticket"]
            Save_Data(self.Settings_Data_Path, Settings_Data)
            
            await Response.edit(embed=Success_Dialog_Embed("이 서버의 티켓 시스템 설정을 초기화했습니다."), view=None)
            Print_Log("Settings", "티켓 시스템 설정을 초기화했습니다.", ctx.guild.name, ctx.author.name)
        except Exception as e:
            await Response.edit(embed=Error_Dialog_Embed(f"티켓 시스템 설정을 초기화하는 중 오류가 발생했습니다. ({e})"), view=None)

    # 인증 시스템 설정 명령어 그룹
    Verify_Settings_CMDGroup = Settings_CMDGroup.create_subgroup("인증")

    # /설정 인증 설정 [역할] [설명]
    @Verify_Settings_CMDGroup.command(name="설정", description="인증 메세지를 생성하고 현재 채널에 전송합니다. 관리자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Setup_Verify_System(self, ctx, Role: discord.Option(discord.Role, name="역할", description="인증 시 부여할 역할을 지정하세요.", required=True),
        Description: discord.Option(str, name="설명", description="인증 메세지의 내용을 지정하세요. (선택)", required=False)):
        
        try:
            Settings_Data = Load_Data(self.Settings_Data_Path)
            Settings_Data.setdefault(str(ctx.guild.id), {})["Verify"] = {"Role_ID": Role.id}
            Save_Data(self.Settings_Data_Path, Settings_Data)
            
            embed = discord.Embed(
                title="멤버 인증",
                description=Description or "✅ 인증하기 버튼을 클릭하여 인증하세요.",
                color=discord.Color.green()
            )
            embed.set_footer(text="인증을 완료하면 서버를 이용하실 수 있습니다.")
            
            await ctx.respond(embed=Success_Dialog_Embed("인증 메세지를 생성했습니다."), ephemeral=True)
            await ctx.channel.send(embed=embed, view=Verify_View())
            Print_Log("Settings", "인증 메세지를 생성했습니다.", ctx.guild.name, ctx.author.name)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"설정을 저장하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /설정 인증 초기화
    @Verify_Settings_CMDGroup.command(name="초기화", description="이 서버의 인증 시스템 설정을 초기화합니다. 서버 소유자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Reset_Verify_System(self, ctx):
        # 권한 확인
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 서버 소유자 권한이 없습니다."), ephemeral=True)

        View = Reset_Confirm_View(ctx.author)
        
        Response = await ctx.respond(embed=discord.Embed(
            title="⚠️ 인증 시스템 초기화",
            description="정말로 이 서버의 인증 시스템 설정을 초기화하시겠습니까? **이 작업은 되돌릴 수 없습니다.**",
            color=discord.Color.red()
        ), view=View, ephemeral=True)
        await View.wait()
        
        if View.Value is None:
            return await Response.edit(embed=Error_Dialog_Embed("시간이 초과되었습니다."), view=None)

        if not View.Value:
            return await Response.edit(embed=Success_Dialog_Embed("인증 시스템 설정 초기화를 취소했습니다."), view=None)

        try:
            Settings_Data = Load_Data(self.Settings_Data_Path)
            Guild_Settings = Settings_Data.get(str(ctx.guild.id), {})

            if "Verify" not in Guild_Settings:
                return await Response.edit(embed=Error_Dialog_Embed("이 서버에 저장된 인증 시스템 설정이 없습니다."), view=None)

            del Guild_Settings["Verify"]
            Save_Data(self.Settings_Data_Path, Settings_Data)

            await Response.edit(embed=Success_Dialog_Embed("이 서버의 인증 시스템 설정을 초기화했습니다."), view=None)
            Print_Log("Settings", "인증 시스템 설정을 초기화했습니다.", ctx.guild.name, ctx.author.name)
        except Exception as e:
            await Response.edit(embed=Error_Dialog_Embed(f"인증 시스템 설정을 초기화하는 중 오류가 발생했습니다. ({e})"), view=None)

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(Verify_View())

def setup(bot):
    bot.add_cog(Settings(bot))