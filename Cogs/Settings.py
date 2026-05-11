import discord, os, json, datetime
from discord.ext import commands
from Resources import Current_Time, Error_Dialog_Embed, Success_Dialog_Embed, Print_Log, Load_Data, Save_Data, Parse_Duration

# 경고 전체 초기화 확인 뷰
class Confirm_Reset_View(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=30)
        self.Author = author
        self.Value = None

    @discord.ui.button(label="예, 진행합니다", style=discord.ButtonStyle.red)
    async def Confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.Author:
            return await interaction.response.send_message("버튼을 조작할 권한이 없습니다.", ephemeral=True)
        self.Value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="아니요", style=discord.ButtonStyle.green)
    async def Cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.Author:
            return await interaction.response.send_message("버튼을 조작할 권한이 없습니다.", ephemeral=True)
        self.Value = False
        await interaction.response.defer()
        self.stop()

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
    async def Reset_All_Warnings(self, ctx):
        # 권한 확인
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 서버 소유자 권한이 없습니다."), ephemeral=True)

        # 확인 Embed
        Confirm_Embed = discord.Embed(
            title="⚠️ 서버 경고 데이터 초기화",
            description="정말로 이 서버의 모든 경고 데이터를 초기화하시겠습니까? **이 작업은 되돌릴 수 없습니다.**",
            color=discord.Color.red()
        )
        View = Confirm_Reset_View(ctx.author)
        
        Response = await ctx.respond(embed=Confirm_Embed, view=View, ephemeral=True)
        
        await View.wait()
        
        if View.Value is None:
            await Response.edit(embed=Error_Dialog_Embed("시간이 초과되어 초기화가 취소되었습니다."), view=None)
        elif View.Value:
            try:
                Warnings = Load_Data(self.Warning_Data_Path)
                Guild_ID = str(ctx.guild.id)
                
                # 해당 서버의 모든 키 삭제
                Keys_to_Delete = [key for key in Warnings.keys() if key.startswith(f"{Guild_ID}_")]
                
                if not Keys_to_Delete:
                    return await Response.edit(embed=Error_Dialog_Embed("이 서버에 저장된 경고 데이터가 없습니다."), view=None)
                
                for key in Keys_to_Delete:
                    del Warnings[key]
                
                Save_Data(self.Warning_Data_Path, Warnings)
                
                await Response.edit(embed=Success_Dialog_Embed("이 서버의 모든 경고 데이터를 초기화했습니다."), view=None)
                Print_Log("Settings", "경고 데이터를 초기화했습니다.", ctx.guild.name, ctx.author.name)
            except Exception as e:
                await Response.edit(embed=Error_Dialog_Embed(f"경고 데이터 초기화 중 오류가 발생했습니다. ({e})"), view=None)
        else:
            await Response.edit(embed=Success_Dialog_Embed("경고 데이터 초기화가 취소되었습니다."), view=None)

    # /설정 경고 자동처벌 [활성화] [횟수] [처벌] [기간]
    @Warning_Settings_CMDGroup.command(name="자동처벌", description="일정 경고 횟수 도달 시 자동으로 부여할 처벌을 설정합니다. 서버 관리자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Auto_Punish_Settings(self, ctx,
        enabled: discord.Option(bool, name="활성화", description="자동 처벌 활성화 여부를 선택하세요."),
        count: discord.Option(int, name="횟수", description="처벌을 실행할 경고 횟수를 지정하세요.", min_value=1),
        action: discord.Option(str, name="처벌", description="자동으로 실행할 처벌의 종류를 선택하세요.", choices=["차단", "추방", "타임아웃"]),
        duration: discord.Option(str, name="기간", description="타임아웃을 부여할 기간을 입력하세요. (선택, ex: 10초, 3분, 1시간, 1일, 1주, 1개월, 1년)", required=False, default="7일")):
        
        # 권한 확인
        if not ctx.author.guild_permissions.administrator:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 서버 관리자 권한이 없습니다."), ephemeral=True)

        # 기간 파싱 확인
        if action == "타임아웃":
            if not Parse_Duration(duration):
                return await ctx.respond(embed=Error_Dialog_Embed("올바른 기간 형식을 입력해주세요. (ex: 10초, 3분, 1시간, 1일, 1주, 1개월, 1년)"), ephemeral=True)

        try:
            Settings = Load_Data(self.Settings_Data_Path)
            Guild_ID = str(ctx.guild.id)
            
            if not enabled:
                if Guild_ID in Settings and "Auto_Punish" in Settings[Guild_ID]:
                    del Settings[Guild_ID]["Auto_Punish"]
                Message = "자동 처벌 설정을 비활성화했습니다."
            else:
                if Guild_ID not in Settings:
                    Settings[Guild_ID] = {}
                
                Settings[Guild_ID]["Auto_Punish"] = {
                    "Enabled": True,
                    "Count": count,
                    "Action": action,
                    "Duration": duration if action == "타임아웃" else None
                }
                Action_Desc = f"**{action}**"
                if action == "타임아웃":
                    Action_Desc += f" ({duration})"
                Message = f"경고 **{count}회** 도달 시 자동으로 {Action_Desc}하도록 설정했습니다."
            
            Save_Data(self.Settings_Data_Path, Settings)
            await ctx.respond(embed=Success_Dialog_Embed(Message), ephemeral=True)
            Print_Log("Settings", "자동 처벌 설정을 변경했습니다.", ctx.guild.name, ctx.author.name, extra=f"상태: {'활성화' if enabled else '비활성화'}, 설정: {Message}")
            
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"설정을 저장하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

def setup(bot):
    bot.add_cog(Settings(bot))