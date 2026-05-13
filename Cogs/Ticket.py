import discord, asyncio, datetime, io
from discord.ext import commands
from Resources import Current_Time, Error_Dialog_Embed, Success_Dialog_Embed, Print_Log, Load_Data, Save_Data

# 티켓 전체 삭제 확인 뷰 클래스
class Ticket_Clean_Confirm_View(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=30)
        self.Author = author
        self.Value = None

    @discord.ui.button(label="예, 모두 삭제합니다", style=discord.ButtonStyle.red)
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

# 티켓 보관 뷰 클래스
class Ticket_Archive_View(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="티켓 삭제", style=discord.ButtonStyle.red, emoji="🗑️", custom_id="ticket_delete")
    async def Delete_Ticket(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("티켓을 삭제할 권한이 없습니다.", ephemeral=True)

        await interaction.response.defer()
        
        # 티켓 아카이브 생성 클래스 호출
        await Generate_Ticket_Archive(interaction.channel, interaction.user)

        await interaction.followup.send(embed=Error_Dialog_Embed("티켓을 영구적으로 삭제합니다. 잠시 후 채널이 삭제됩니다."))
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"티켓 삭제 (요청자: {requester.name})")
        except:
            pass

# 티켓 아카이브 생성 및 전송 클래스
async def Generate_Ticket_Archive(channel: discord.TextChannel, requester: discord.User):
    try:
        Messages = []
        async for msg in channel.history(limit=None, oldest_first=True):
            Timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            Content = msg.clean_content if msg.clean_content else ( "[파일 또는 Embed 메시지]" if msg.attachments or msg.embeds else "" )
            Messages.append(f"[{Timestamp}] {msg.author.display_name} ({msg.author.id}): {Content}")
        
        Log_Content = "------------------------------------------\n"
        Log_Content += f"티켓 아카이브 | {channel.name}\n"
        Log_Content += f"티켓 삭제 일시 | {Current_Time()}\n"
        Log_Content += f"티켓 삭제 요청자 | {requester.display_name} ({requester.id})\n"
        Log_Content += "------------------------------------------\n\n"
        Log_Content += "\n".join(Messages)
        
        Log_File = discord.File(io.BytesIO(Log_Content.encode("utf-8")), filename=f"{channel.name}_Archive.txt")
        
        # 설정 불러오기
        Settings = Load_Data("Datas/Settings_Data.json")
        Guild_ID = str(channel.guild.id)
        Log_Channel_ID = Settings.get(Guild_ID, {}).get("Ticket", {}).get("Log_Channel_ID")
        Log_Channel = channel.guild.get_channel(Log_Channel_ID)
        
        if Log_Channel:
            Embed = discord.Embed(
                title="💬 티켓 로그 아카이브",
                description=f"`{channel.name}` 티켓이 {requester.mention}님에 의해 삭제되었습니다.\n위의 텍스트 파일은 전체 대화 내역입니다.",
                color=discord.Color.blue()
            )
            await Log_Channel.send(embed=Embed, file=Log_File)
            Print_Log("Ticket", f"티켓을 삭제했습니다.", channel.guild.name, requester.name)
            return True
    except Exception as e:
        Print_Log("Ticket", f"티켓 아카이브를 생성하는 중 오류가 발생했습니다.", channel.guild.name, "애플리케이션", "(e)")
    return False

# 티켓 컨트롤 뷰 클래스
class Ticket_Control_View(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="티켓 보관", style=discord.ButtonStyle.red, emoji="📥", custom_id="ticket_close")
    async def Close_Ticket(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("티켓을 보관할 권한이 없습니다.", ephemeral=True)

        Settings = Load_Data("Datas/Settings_Data.json")
        Guild_ID = str(interaction.guild.id)
        Archive_Category_ID = Settings.get(Guild_ID, {}).get("Ticket", {}).get("Archive_Category_ID")
        Archive_Category = interaction.guild.get_channel(Archive_Category_ID) if Archive_Category_ID else None

        await interaction.response.defer()

        Current_Name = interaction.channel.name
        # 채널 이름 변경
        Clean_Name = Current_Name.replace('ticket-', '')
        New_Name = f"closed-{Clean_Name}"

        embed = discord.Embed(
            title="📥 티켓이 보관되었습니다.",
            description=f"{interaction.user.mention}님이 티켓을 보관했습니다.",
            color=discord.Color.blue()
        )
        
        try:
            await interaction.channel.edit(
                name=New_Name,
                category=Archive_Category,
                sync_permissions=False if Archive_Category else True,
                reason=f"티켓 보관 (요청자: {interaction.user.name})"
            )
            
            for target, overwrite in interaction.channel.overwrites.items():
                if isinstance(target, discord.Member) and not target.bot:
                    overwrite.view_channel = False
                    await interaction.channel.set_permissions(target, overwrite=overwrite)

            await interaction.channel.send(embed=embed, view=Ticket_Archive_View())
            Print_Log("Ticket", "티켓을 보관했습니다.", interaction.guild.name, interaction.user.name)
            
        except Exception as e:
            await interaction.followup.send(embed=Error_Dialog_Embed(f"티켓을 보관하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

# 티켓 보드 뷰 클래스
class Ticket_Board_View(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="티켓 생성", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="ticket_open")
    async def Open_Ticket(self, button: discord.ui.Button, interaction: discord.Interaction):
        Guild = interaction.guild
        User = interaction.user
        
        Settings = Load_Data("Datas/Settings_Data.json")
        Guild_ID = str(Guild.id)
        
        if Guild_ID not in Settings: Settings[Guild_ID] = {}
        if "Ticket" not in Settings[Guild_ID]: Settings[Guild_ID]["Ticket"] = {}
        
        Last_ID = Settings[Guild_ID]["Ticket"].get("Last_ID", 0)
        New_ID = Last_ID + 1
        Settings[Guild_ID]["Ticket"]["Last_ID"] = New_ID
        Save_Data("Datas/Settings_Data.json", Settings)
        
        Formatted_ID = str(New_ID).zfill(4)
        
        Category_ID = Settings[Guild_ID]["Ticket"].get("Category_ID")
        Staff_Role_ID = Settings[Guild_ID]["Ticket"].get("Staff_Role_ID")
        
        Category = Guild.get_channel(Category_ID) if Category_ID else None
        Staff_Role = Guild.get_role(Staff_Role_ID) if Staff_Role_ID else None

        Overwrites = {
            Guild.default_role: discord.PermissionOverwrite(view_channel=False),
            User: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            Guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)
        }
        
        if Staff_Role:
            Overwrites[Staff_Role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            Ticket_Channel = await Guild.create_text_channel(
                name=f"ticket-{Formatted_ID}",
                category=Category,
                overwrites=Overwrites,
                reason=f"티켓 생성 (요청자: {User.name})"
            )
            
            embed = discord.Embed(
                title=f"🎫 티켓을 생성했습니다.",
                description=f"{User.mention}님, 문의 내용을 작성해주시면 {Staff_Role.mention if Staff_Role else '관리자'}이(가) 확인 후 답변해 드리겠습니다.",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"일시: {Current_Time()}")
            
            await Ticket_Channel.send(embed=embed, view=Ticket_Control_View())
            await interaction.response.send_message(embed=Success_Dialog_Embed(f"티켓이 생성되었습니다: {Ticket_Channel.mention}"), ephemeral=True)
            Print_Log("Ticket", "티켓을 생성했습니다.", Guild.name, User.name)
            
        except Exception as e:
            await interaction.response.send_message(embed=Error_Dialog_Embed(f"티켓을 생성하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.Settings_Data_Path = "Datas/Settings_Data.json"

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(Ticket_Board_View())
        self.bot.add_view(Ticket_Control_View())
        self.bot.add_view(Ticket_Archive_View())

    Ticket_CMDGroup = discord.SlashCommandGroup("티켓")

    @Ticket_CMDGroup.command(name="보드", description="티켓 보드를 현재 채널에 전송합니다. 관리자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Send_Panel(self, ctx):
        # 설정 불러오기
        Settings = Load_Data(self.Settings_Data_Path)
        Guild_ID = str(ctx.guild.id)
        Ticket_Settings = Settings.get(Guild_ID, {}).get("Ticket", {})
        
        # 설정 확인
        Required_Keys = ["Category_ID", "Archive_Category_ID", "Staff_Role_ID"]
        if not all(Ticket_Settings.get(key) for key in Required_Keys):
            return await ctx.respond(embed=Error_Dialog_Embed("티켓 시스템이 설정되어 있지 않습니다. `/설정 티켓 설정` 명령어를 통해 먼저 티켓 시스템 설정을 완료해주세요."), ephemeral=True)

        embed = discord.Embed(
            title="🎫 서버 문의",
            description="도움이 필요하거나 문의 사항이 있으시다면 아래 버튼을 눌러 티켓을 생성하세요.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="티켓을 생성하면 티켓 생성자와 서버 관리자만 접근할 수 있는 비공개 채널이 생성됩니다.")
        await ctx.respond(embed=Success_Dialog_Embed("티켓 보드를 전송했습니다."), ephemeral=True)
        await ctx.channel.send(embed=embed, view=Ticket_Board_View())

    @Ticket_CMDGroup.command(name="삭제", description="보관된 모든 티켓을 삭제합니다. 관리자 권한을 요구합니다.")
    @discord.default_permissions(administrator=True)
    async def Purge_Tickets(self, ctx):
        # 설정 불러오기
        Settings = Load_Data(self.Settings_Data_Path)
        Guild_ID = str(ctx.guild.id)
        Archive_Category_ID = Settings.get(Guild_ID, {}).get("Ticket", {}).get("Archive_Category_ID")
        Archive_Category = ctx.guild.get_channel(Archive_Category_ID)

        # 보관 카테고리 확인
        if not Archive_Category:
            return await ctx.respond(embed=Error_Dialog_Embed("보관 카테고리가 설정되어 있지 않습니다."), ephemeral=True)

        # 보관된 티켓 채널 확인
        Target_Channels = [Channel for Channel in Archive_Category.channels if isinstance(Channel, discord.TextChannel) and Channel.name.startswith("closed-")]
        
        if not Target_Channels:
            return await ctx.respond(embed=Error_Dialog_Embed("보관된 티켓이 없습니다."), ephemeral=True)

        # 티켓 전체 삭제 확인
        Confirm_Embed = discord.Embed(
            title="🗑️ 티켓 전체 삭제",
            description=f"정말로 보관된 티켓 **{len(Target_Channels)}개**를 모두 삭제하시겠습니까? **로그 채널이 지정된 경우 모든 티켓의 대화 내역이 로그 채널에 아카이브됩니다.**",
            color=discord.Color.red()
        )
        View = Ticket_Clean_Confirm_View(ctx.author)
        await ctx.respond(embed=Confirm_Embed, view=View, ephemeral=True)
        await View.wait()

        # 티켓 전체 삭제 실행
        if View.Value:
            Deleted_Count = 0
            Progress_Msg = await ctx.followup.send(embed=Success_Dialog_Embed(f"티켓 전체 삭제를 시작합니다. (0/{len(Target_Channels)})"), ephemeral=True)
            
            for Channel in Target_Channels:
                try:
                    # 티켓 아카이브 생성
                    await Generate_Ticket_Archive(Channel, ctx.author)
                    # 채널 삭제
                    await Channel.delete(reason=f"티켓 전체 삭제 (요청자: {ctx.author.name})")
                    Deleted_Count += 1
                    
                    # 진행률 표시
                    if Deleted_Count % 5 == 0:
                        await Progress_Msg.edit(embed=Success_Dialog_Embed(f"티켓 전체 삭제를 진행 중입니다. ({Deleted_Count}/{len(Target_Channels)})"))
                except:
                    continue
            
            await Progress_Msg.edit(embed=Success_Dialog_Embed(f"보관된 티켓 **{Deleted_Count}개**를 모두 삭제했습니다."), view=None)
            Print_Log("Ticket", "티켓을 모두 삭제했습니다.", ctx.guild.name, ctx.author.name)
        else:
            await ctx.followup.edit(embed=Success_Dialog_Embed("티켓 전체 삭제를 취소했습니다."), view=None)

def setup(bot):
    bot.add_cog(Ticket(bot))