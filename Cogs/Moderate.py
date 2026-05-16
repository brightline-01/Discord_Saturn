import discord, asyncio, json, re, datetime
from Resources import Current_Time, Error_Dialog_Embed, Success_Dialog_Embed, Print_Log, Load_Data, Save_Data, Parse_Duration
from discord.ext import commands

# 경고 목록 페이지 뷰 클래스
class Warning_Page_View(discord.ui.View):
    def __init__(self, member, reasons, timeout=60):
        super().__init__(timeout=timeout)
        self.Target_Member = member
        self.Reasons = list(reversed(reasons)) # 최신순 정렬
        self.Current_Page = 0
        self.Items_per_Page = 10
        self.Max_Page = (len(self.Reasons) - 1) // self.Items_per_Page if reasons else 0
        self.Update_Buttons()

    def Create_Embed(self):
        Start = self.Current_Page * self.Items_per_Page
        Current_Reasons = self.Reasons[Start:Start + self.Items_per_Page]
        
        embed = discord.Embed(title=f"⚠️ {self.Target_Member.display_name}님의 경고 목록",
                            color=discord.Color.yellow(),
                            description="표시할 경고 목록이 없습니다." if not Current_Reasons else None)
        
        for Index, Reason in enumerate(Current_Reasons, Start + 1):
            embed.add_field(name=f"{Index}. {Reason['Reason']}", value=f"요청자: {Reason['Issuer']} | 일시: {Reason['Time']}", inline=False)
            
        embed.set_thumbnail(url=self.Target_Member.display_avatar.url)
        embed.set_footer(text=f"페이지 {self.Current_Page + 1}/{self.Max_Page + 1} | 일시: {Current_Time()}")
        return embed

    def Update_Buttons(self):
        # 버튼 활성화/비활성화 상태 업데이트
        self.Prev_Button.disabled = self.Current_Page <= 0
        self.Next_Button.disabled = self.Current_Page >= self.Max_Page

    async def Change_Page(self, interaction, Offset):
        New_Page = self.Current_Page + Offset

        if 0 <= New_Page <= self.Max_Page:
            self.Current_Page = New_Page
            self.Update_Buttons()

            await interaction.response.edit_message(embed=self.Create_Embed(), view=self)

    @discord.ui.button(label="이전", style=discord.ButtonStyle.gray)
    async def Prev_Button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.Change_Page(interaction, -1)

    @discord.ui.button(label="다음", style=discord.ButtonStyle.gray)
    async def Next_Button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.Change_Page(interaction, 1)

class Moderate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.Timeout_Data_Path = "Datas/Timeout_Data.json"
        self.Warning_Data_Path = "Datas/Warning_Data.json"
        self.Settings_Data_Path = "Datas/Settings_Data.json"
        self.Timeout_Tasks = {}
        self.Message_Cache = {}
        self.Channel_Cache = {}
        
        # 애플리케이션이 실행되면 저장된 타임아웃 정보를 복원
        self.bot.loop.create_task(self.Restore_Timeouts())

    # 도배 감지 엔진
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild or message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages:
            return

        # 설정 불러오기
        Config = (Load_Data(self.Settings_Data_Path).get(str(message.guild.id), {}).get("Anti_Spam", {}))
        
        if not Config or not Config.get("Enabled"):
            return
        
        # 메시지 기록 업데이트
        Now = datetime.datetime.now().timestamp()
        User_Key = (message.guild.id, message.author.id)
        
        Cache = self.Message_Cache.setdefault(User_Key, [])
        Cache.append((Now, message.content))

        Threshold_Seconds = Config["Seconds"]
        Cache[:] = [item for item in Cache if Now - item[0] <= Threshold_Seconds]
        Same_Message_Mode = Config.get("Mode") == "동일한 메세지"
        Spam_Count = sum(Content == message.content for _, Content in Cache) if Same_Message_Mode else len(Cache)

        if Spam_Count < Config["Count"]:
            return

        del self.Message_Cache[User_Key]

        Reason_Text = f"동일한 내용 도배 ({Threshold_Seconds}초 내 {Spam_Count}회)" if Same_Message_Mode else f"메시지 과다 전송 ({Threshold_Seconds}초 내 {Spam_Count}회)"
        
        await self.Execute_Anti_Spam_Punishment(message, Config, Reason_Text)

    async def Execute_Anti_Spam_Punishment(self, message, Config, Reason_Text):
        Action = Config["Action"]
        Duration_Str = Config.get("Duration")
        Reason = f"[자동 처벌] {Reason_Text}"

        try:
            Actions = {"차단": lambda: message.author.ban(reason=Reason, delete_message_days=1), "추방": lambda: message.author.kick(reason=Reason),
                "타임아웃": lambda: message.author.timeout_for(Parse_Duration(Duration_Str),reason=Reason)}

            if Action == "타임아웃" and not Parse_Duration(Duration_Str):
                return

            await Actions[Action]()

            Punish_Text = {"차단": "차단", "추방": "추방", "타임아웃": f"{Duration_Str}간 타임아웃"}[Action]

            await message.channel.send(embed=Success_Dialog_Embed(f"{message.author.display_name}님을 **{Punish_Text}**했습니다."))
            Print_Log("Moderate", f"자동 처벌 ({Action})을 실행했습니다.", message.guild.name, "애플리케이션 (도배 감지)", message.author.name, Extra=f"감지 사유: {Reason_Text}")
        except Exception as e:
            Print_Log("Moderate", "자동 처벌 중 오류가 발생했습니다.", message.guild.name, "애플리케이션 (도배 감지)", message.author.name, Extra=f"오류: {e}")

    # 권한 부여 감지
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if not after.guild or len(before.roles) >= len(after.roles):
            return

        if not any(role.permissions.administrator for role in after.roles if role not in before.roles):
            return

        Config = (Load_Data(self.Settings_Data_Path).get(str(after.guild.id), {}).get("Anti_Admin", {}))

        if not Config.get("Enabled"):
            return

        try:
            async for Entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
                if Entry.target.id != after.id:
                    continue

                Issuer = Entry.user

                if Issuer.id in {after.guild.owner_id, self.bot.user.id}:
                    return

                Reason = f"[권한 부여 감지] 승인되지 않은 관리자 권한 부여 (부여자: {Issuer.name})"

                if after.id != after.guild.owner_id:
                    await after.ban(reason=Reason)

                if Issuer.id != after.guild.owner_id:
                    await Issuer.ban(reason=Reason)

                Print_Log("Moderate", "사용자를 차단했습니다.", after.guild.name, "애플리케이션 (권한 부여 감지)", after.name, Extra=f"부여자: {Issuer.name}")
                break

        except Exception as e:
            Print_Log("Moderate", "사용자를 차단하는 중 오류가 발생했습니다.", after.guild.name, "애플리케이션 (권한 부여 감지)", after.name, Extra=f"오류: {e}")

    # 레이드 감지 엔진
    async def Check_Channel_Raid(self, guild, action_type):
        try:
            Config = Load_Data(self.Settings_Data_Path).get(str(guild.id), {}).get("Anti_Channel")
            if not Config or not Config.get("Enabled"):
                return

            Threshold_Count = Config["Count"]
            Threshold_Seconds = Config["Seconds"]
            Audit_Action = discord.AuditLogAction.channel_create if action_type == "create" else discord.AuditLogAction.channel_delete

            async for entry in guild.audit_logs(limit=3, action=Audit_Action):
                Issuer = entry.user

                if Issuer.id in {self.bot.user.id, guild.owner_id}:
                    continue

                User_Key = (guild.id, Issuer.id)
                Now = datetime.datetime.now().timestamp()

                Cache = self.Channel_Cache.setdefault(User_Key, [])
                Cache.append(Now)

                self.Channel_Cache[User_Key] = [ts for ts in Cache if Now - ts <= Threshold_Seconds]

                if len(self.Channel_Cache[User_Key]) < Threshold_Count:
                    continue

                del self.Channel_Cache[User_Key]

                Action_Text = "생성" if action_type == "create" else "삭제"
                Reason = f"[레이드 감지] 지정한 시간 내 다발적 채널 {Action_Text} 감지 ({Threshold_Seconds}초 내 {Threshold_Count}회 이상)"

                await Issuer.ban(reason=Reason)

                Print_Log("Moderate", "사용자를 차단했습니다.", guild.name, "애플리케이션 (레이드 감지)", Issuer.name, Extra=f"작업: 채널 {action_type}")
                break
        except Exception as e:
            Print_Log("Moderate", "사용자를 차단하는 중 오류가 발생했습니다.", guild.name, "애플리케이션 (레이드 감지)", Extra=f"오류: {e}")

    # 채널 생성 감지
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await self.Check_Channel_Raid(channel.guild, "create")

    # 채널 삭제 감지
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await self.Check_Channel_Raid(channel.guild, "delete")

    # 애플리케이션 재시작 시 타임아웃 정보 불러오기 스크립트
    async def Restore_Timeouts(self):
        await self.bot.wait_until_ready()

        Timeouts = Load_Data(self.Timeout_Data_Path)

        if not Timeouts:
            return

        print(f"[Moderate] 타임아웃 정보를 불러왔습니다.")

        Now = datetime.datetime.now()

        for Key, Info in list(Timeouts.items()):
            Guild = self.bot.get_guild(Info.get('Guild_ID'))
            Member = Guild.get_member(Info.get('Member_ID'))

            if not Member:
                del Timeouts[Key]
                continue

            # 남은 전체 기간 계산
            Target_End = datetime.datetime.fromisoformat(Info.get('Target_End'))

            if Target_End.tzinfo is None:
                Target_End = Target_End.replace(tzinfo=datetime.timezone.utc)
            
            Remaining = Target_End - Now

            if Remaining.total_seconds() <= 0 or not Member.communication_disabled_until:
                del Timeouts[Key]
                continue

            Applied_Remaining = Member.communication_disabled_until - datetime.datetime.now()
            Task_Key = f"{Guild.id}_{Member.id}"

            if Task := self.Timeout_Tasks.get(Task_Key):
                Task.cancel()

            self.Timeout_Tasks[Task_Key] = self.bot.loop.create_task(self.Auto_Extend_Timeout(Member, Applied_Remaining, Remaining, Info.get('Reason', '사유 없음')))

        Save_Data(self.Timeout_Data_Path, Timeouts)
    
    # 역할 제어
    async def Control_Role(ctx, Member, Role, Reason, Remove=False):
        Action = "해제" if Remove else "부여"

        if not ctx.author.guild_permissions.manage_roles:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 역할 관리하기 권한이 없습니다."), ephemeral=True)

        if ctx.author.id != ctx.guild.owner_id and Role.position >= ctx.author.top_role.position:
            return await ctx.respond(embed=Error_Dialog_Embed(f"사용자 본인의 최상위 역할보다 높거나 같은 역할은 {Action}할 수 없습니다."), ephemeral=True)

        if Role.position >= ctx.guild.me.top_role.position:
            return await ctx.respond(embed=Error_Dialog_Embed(f"애플리케이션의 최상위 역할보다 높거나 같은 역할은 {Action}할 수 없습니다."), ephemeral=True)

        Has_Role = Role in Member.roles

        if Remove and not Has_Role:
            return await ctx.respond(embed=Error_Dialog_Embed("이미 해당 역할을 보유하고 있지 않은 사용자입니다."), ephemeral=True)
        
        if not Remove and Has_Role:
            return await ctx.respond(embed=Error_Dialog_Embed("이미 해당 역할을 보유하고 있는 사용자입니다."), ephemeral=True)

        try:
            Method = Member.remove_roles if Remove else Member.add_roles
            await Method(Role, reason=f"{Reason} (요청자: {ctx.author.display_name})")
            
            embed = discord.Embed(title=f"✅ {Member.display_name}님에게 {Action}했습니다.", color=discord.Color.green())
            embed.add_field(name="역할", value=Role.mention, inline=True)
            embed.add_field(name="사유", value=Reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=Member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{Member.display_name}님에게 {Action}했습니다.", ctx.guild.name, ctx.author.name, Member.name)
        # 애플리케이션 권한 예외 처리
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed(f"애플리케이션에게 해당 멤버의 역할을 {Action}할 권한이 없습니다."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"역할을 {Action}하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # 사용자 ID 파싱
    def Parse_User_ID(user: str):
        Match = re.search(r"\d+", user)
        return int(Match.group()) if Match else None

    # 관리 메세지 임베드 생성
    async def Create_Moderate_Embed(ctx, title, member, reason, color):
        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="사용자", value=member.display_name, inline=True)
        embed.add_field(name="사유", value=reason, inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"일시: {Current_Time()}")
        await ctx.respond(embed=embed)

    # 경고 데이터 불러오기
    def Get_Warning_Data(self, guild_id, member_id):
        Warnings = Load_Data(self.Warning_Data_Path)
        User_Key = f"{guild_id}_{member_id}"

        if User_Key not in Warnings:
            Warnings[User_Key] = {"Count": 0, "Reasons": []}

        return Warnings, User_Key, Warnings[User_Key]

    # 자동 처벌 실행
    async def Run_Auto_Punish(self, ctx, Member, Count):
        try:
            Config = Load_Data(self.Settings_Data_Path).get(str(ctx.guild.id), {}).get("Auto_Punish")

            if not Config or not Config.get("Enabled") or Count < Config["Count"]:
                return

            Action = Config["Action"]
            Reason = f"[자동 처벌] 경고 {Config['Count']}회 누적 (현재 경고 횟수: {Count}회)"

            Punishments = {
                "차단": lambda: Member.ban(reason=Reason, delete_message_days=0),
                "추방": lambda: Member.kick(reason=Reason),
                "타임아웃": lambda: Member.timeout_for(Parse_Duration(Config["Duration"]), reason=Reason)
            }

            if Action == "타임아웃" and not Parse_Duration(Config["Duration"]):
                return

            await Punishments[Action]()
            await ctx.send(embed=Success_Dialog_Embed(f"{Member.display_name}님을 자동으로 {Action}했습니다."))

            Print_Log("Moderate", f"자동 처벌을 실행했습니다.", ctx.guild.name, "애플리케이션 (자동 처벌)", Member.name, Extra=f"처벌: {Action}, 현재 경고 횟수: {Count}회")
        except Exception as e:
            Print_Log("Moderate", "자동 처벌 실행 중 오류가 발생했습니다.", ctx.guild.name, "애플리케이션 (자동 처벌)", Member.name, Extra=f"({e})")

    Moderate_CMDGroup = discord.SlashCommandGroup("관리")

    # /관리 추방 [@사용자] [사유]
    @Moderate_CMDGroup.command(name="추방", description="사용자를 서버에서 추방합니다. 멤버 추방 권한을 요구합니다.")
    @discord.default_permissions(kick_members=True)
    async def Kick_Member(self, ctx, Member: discord.Option(discord.Member, name="사용자", description="추방할 사용자를 지정하세요."),
        Reason: discord.Option(str, name="사유", description="추방할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.kick_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 추방 권한이 없습니다."), ephemeral=True)

        if Member == ctx.author:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자가 스스로를 추방할 수 없습니다."), ephemeral=True)

        if Member == self.bot.user:
            return await ctx.respond(embed=Error_Dialog_Embed("애플리케이션이 스스로를 추방할 수 없습니다."), ephemeral=True)

        # 추방 실행
        try:
            await Member.kick(reason=f"{Reason} (요청자: {ctx.author.display_name})")
            await self.Create_Moderate_Embed(ctx, f"⚠️ {Member.display_name}님을 서버에서 추방했습니다.", Member, Reason, discord.Color.red())
            Print_Log("Moderate", f"{Member.display_name}님을 추방했습니다.", ctx.guild.name, ctx.author.name, Member.name)
        # 애플리케이션 권한 예외 처리
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 멤버를 추방할 권한이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"추방 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    Ban_CMDGroup = Moderate_CMDGroup.create_subgroup("차단")

    # /관리 차단 부여 [@사용자 / 사용자 ID] [사유] [메세지 (예/아니요)]
    @Ban_CMDGroup.command(name="부여", description="사용자를 서버에서 차단합니다. 멤버 차단하기 권한을 요구합니다.")
    @discord.default_permissions(ban_members=True)
    async def Ban_Member(self, ctx,
        User: discord.Option(str, name="사용자", description="차단할 사용자의 멘션 또는 사용자 ID를 입력하세요."),
        Reason: discord.Option(str, name="사유", description="차단할 사유를 지정하세요. (선택)", required=False, default="사유 없음"),
        Delete_Messages: discord.Option(bool, name="메세지", description="차단할 사용자의 모든 메세지를 삭제합니다. (선택)", required=False, default=False)):

        User_ID = self.Parse_User_ID(User)

        if not User_ID:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자를 찾을 수 없습니다. 올바른 사용자 멘션 또는 ID를 입력해주세요."), ephemeral=True)

        # 요청자 권한 확인
        if not ctx.author.guild_permissions.ban_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 차단하기 권한이 없습니다."), ephemeral=True)

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
            await ctx.guild.ban(Target_User, reason=f"{Reason} (요청자: {ctx.author.display_name})")
            await self.Create_Moderate_Embed(ctx, f"⚒️ {Target_User.display_name}님을 서버에서 차단했습니다.", Target_User, Reason, discord.Color.red())
            Print_Log("Moderate", f"{Target_User.display_name}님을 차단했습니다.", ctx.guild.name, ctx.author.name, Target_User.name)

            # 서버 멤버인 경우, 메세지 삭제를 선택한 경우 차단 대상 멤버가 전송한 모든 메세지 삭제
            if Delete_Messages and ctx.guild.get_member(User_ID):
                Deleted_Messages = 0
                for channel in ctx.guild.text_channels:
                    try:
                        Deleted_Messages += len(await channel.purge(limit=None, check=lambda message: message.author.id == User_ID, reason="멤버 차단으로 인한 메세지 삭제"))
                    except:
                        pass
                Print_Log("Moderate", "메세지를 삭제했습니다.", ctx.guild.name, "시스템 (차단)", Target_User.name, f"삭제된 메세지: {Deleted_Messages}개")
        # 애플리케이션 권한 예외 처리
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 사용자를 차단할 권한이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"차단 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /관리 차단 해제 [@사용자 / 사용자 ID] [사유]
    @Ban_CMDGroup.command(name="해제", description="사용자의 차단을 해제합니다. 멤버 차단하기 권한을 요구합니다.")
    @discord.default_permissions(ban_members=True)
    async def Unban_Member(self, ctx,
        user: discord.Option(str, name="사용자", description="차단을 해제할 사용자의 멘션 또는 사용자 ID를 입력하세요."),
        reason: discord.Option(str, name="사유", description="차단을 해제할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        User_ID = self.Parse_User_ID(user)

        if not User_ID:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자를 찾을 수 없습니다. 올바른 사용자 멘션 또는 ID를 입력해주세요."), ephemeral=True)

        # 차단 해제 실행
        try:
            Target_User = await self.bot.fetch_user(User_ID)
            await ctx.guild.unban(Target_User, reason=reason)
            await self.Create_Moderate_Embed(ctx, f"✅ {Target_User.display_name}님의 차단을 해제했습니다.", Target_User, reason, discord.Color.green())
            Print_Log("Moderate", f"{Target_User.name}님의 차단을 해제했습니다.", ctx.guild.name, ctx.author.name, Target_User.name)
        except discord.NotFound:
            await ctx.respond(embed=Error_Dialog_Embed("이미 차단 해제된 사용자입니다."), ephemeral=True)
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 사용자의 차단을 해제할 권한이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"차단 해제 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    Timeout_CMDGroup = Moderate_CMDGroup.create_subgroup("타임아웃")

    # 타임아웃 자동 연장 스크립트
    async def Auto_Extend_Timeout(self, Member: discord.Member, Applied: datetime.timedelta, Remaining: datetime.timedelta, Reason: str):
        Task_Key = f"{Member.guild.id}_{Member.id}"
        try:
            while Remaining.total_seconds() > 0:
                # 현재 적용된 타임아웃이 종료되기 10초 전까지 대기
                await asyncio.sleep(max(Applied.total_seconds() - 10, 0))

                # 정확한 대기를 위해 멤버 객체 갱신 및 재확인
                Member = await Member.guild.fetch_member(Member.id)
                if not Member or not Member.is_timed_out():
                    break

                # 다음 연장 기간 계산 (최대 28일)
                Applied = min(Remaining, datetime.timedelta(days=28))
                Remaining -= Applied
                
                try:
                    await Member.timeout(Applied, reason=f"[자동 연장] {Reason}")
                    Print_Log("Moderate", "타임아웃을 자동으로 연장했습니다.", Member.guild.name, "시스템 (자동 연장)", Member.name, f"남은 기간: {Remaining}")
                except discord.Forbidden:
                    Print_Log("Moderate", "타임아웃 자동 연장에 실패했습니다.", Member.guild.name, "시스템 (자동 연장)", Member.name, "사유: 권한 부족")
                    break
        except asyncio.CancelledError:
            Print_Log("Moderate", "타임아웃 자동 연장 작업이 취소되었습니다.", Member.guild.name, "시스템 (자동 연장)", Member.name)
        except Exception as e:
            Print_Log("Moderate", "타임아웃 자동 연장 중 오류가 발생했습니다.", Member.guild.name, "시스템 (자동 연장)", Member.name, f"오류: {e}")
        finally:
            # 작업 종료 시 데이터베이스 및 태스크 관리 정리
            Timeouts = Load_Data(self.Timeout_Data_Path)
            if Remaining.total_seconds() <= 0:
                Timeouts.pop(Task_Key, None)
                Save_Data(self.Timeout_Data_Path, Timeouts)
            
            self.Timeout_Tasks.pop(Task_Key, None)

    # /관리 타임아웃 부여 [@사용자] [기간] [사유]
    @Timeout_CMDGroup.command(name="부여", description="사용자를 타임아웃합니다. 타임아웃 멤버 권한을 요구합니다.")
    @discord.default_permissions(moderate_members=True)
    async def Timeout_Member(self, ctx, Member: discord.Option(discord.Member, name="사용자", description="타임아웃할 사용자를 지정하세요."),
        Duration: discord.Option(str, name="기간", description="타임아웃할 기간을 입력하세요. (ex: 10초, 3분, 1시간, 1일, 1주, 1개월, 1년)"),
        Reason: discord.Option(str, name="사유", description="타임아웃할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.moderate_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 타임아웃 권한이 없습니다."), ephemeral=True)

        if Member == ctx.author:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자가 스스로를 타임아웃할 수 없습니다."), ephemeral=True)

        if Member == self.bot.user:
            return await ctx.respond(embed=Error_Dialog_Embed("애플리케이션을 타임아웃할 수 없습니다."), ephemeral=True)

        # 타임아웃 기간 파싱
        Duration_Delta = Parse_Duration(Duration)
        if not Duration_Delta:
            return await ctx.respond(embed=Error_Dialog_Embed("올바른 기간 형식을 입력해주세요. (ex: 10초, 3분, 1시간, 1일, 1주, 1개월, 1년)"), ephemeral=True)

        Task_Key = f"{ctx.guild.id}_{Member.id}"
        Final_End = datetime.datetime.now() + Duration_Delta
        Max_Duration = datetime.timedelta(days=28)
        Applied = min(Duration_Delta, Max_Duration)

        try:
            if Task := self.Timeout_Tasks.pop(Task_Key, None):
                Task.cancel()

            await Member.timeout_for(Applied, reason=f"{Reason} (요청자: {ctx.author.display_name})")

            if Duration_Delta > Max_Duration:
                Timeouts = Load_Data(self.Timeout_Data_Path)
                Timeouts[Task_Key] = {"Guild_ID": ctx.guild.id, "Member_ID": Member.id, "Target_End": Final_End.isoformat(), "Reason": Reason}

                Save_Data(self.Timeout_Data_Path, Timeouts)

                self.Timeout_Tasks[Task_Key] = self.bot.loop.create_task(self.Auto_Extend_Timeout(Member, Applied, Duration_Delta - Max_Duration, Reason))

            embed = discord.Embed(title=f"🔇 {Member.display_name}님을 타임아웃했습니다.", color=discord.Color.yellow())
            embed.add_field(name="사유", value=Reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.add_field(name="기간", value=f"{Final_End.strftime('%Y년 %m월 %d일 %H:%M:%S')}까지", inline=True)
            embed.set_thumbnail(url=Member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{Member.display_name}님을 타임아웃했습니다.", ctx.guild.name, ctx.author.name, Member.name, f"기간: {Final_End.strftime('%Y년 %m월 %d일 %H:%M:%S')}까지")
        # 애플리케이션 권한 예외 처리
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 멤버를 타임아웃할 권한이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"타임아웃 부여 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /관리 타임아웃 해제 [@사용자] [사유]
    @Timeout_CMDGroup.command(name="해제", description="사용자의 타임아웃을 해제합니다. 타임아웃 멤버 권한을 요구합니다.")
    @discord.default_permissions(moderate_members=True)
    async def Untimeout_Member(self, ctx, Member: discord.Option(discord.Member, name="사용자", description="타임아웃을 해제할 사용자를 지정하세요."),
        Reason: discord.Option(str, name="사유", description="타임아웃을 해제할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.moderate_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 타임아웃 권한이 없습니다."), ephemeral=True)

        if not Member.timed_out:
            return await ctx.respond(embed=Error_Dialog_Embed("이미 타임아웃 상태가 아닌 사용자입니다."), ephemeral=True)

        # 타임아웃 해제 실행
        try:
            await Member.timeout(None, reason=f"{Reason} (요청자: {ctx.author.display_name})")
            
            # 자동 연장 데이터 및 태스크 삭제
            Task_Key = f"{ctx.guild.id}_{Member.id}"

            if Task := self.Timeout_Tasks.pop(Task_Key, None):
                Task.cancel()

            Timeouts = Load_Data(self.Timeout_Data_Path)
            if Task_Key in Timeouts:
                del Timeouts[Task_Key]
                Save_Data(self.Timeout_Data_Path, Timeouts)

            embed = discord.Embed(title=f"🔊 {Member.display_name}님의 타임아웃을 해제했습니다.", color=discord.Color.green())
            embed.add_field(name="사유", value=Reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=Member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{Member.display_name}님의 타임아웃을 해제했습니다.", ctx.guild.name, ctx.author.name, Member.name)
        # 애플리케이션 권한 예외 처리
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 멤버의 타임아웃을 해제할 권한이 없습니다."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"타임아웃 해제 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    Role_CMDGroup = Moderate_CMDGroup.create_subgroup("역할")

    # /관리 역할 부여 [@사용자] [@역할] [사유]
    @Role_CMDGroup.command(name="부여", description="사용자에게 역할을 부여합니다. 역할 관리하기 권한을 요구합니다.")
    @discord.default_permissions(manage_roles=True)
    async def Give_Role_Member(self, ctx, Member: discord.Option(discord.Member, name="사용자", description="역할을 부여할 사용자를 지정하세요."),
        Role: discord.Option(discord.Role, name="역할", description="부여할 역할을 지정하세요."),
        Reason: discord.Option(str, name="사유", description="부여할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        await Control_Role(ctx, Member, Role, Reason)

    # /관리 역할 해제 [@사용자] [@역할] [사유]
    @Role_CMDGroup.command(name="해제", description="사용자의 역할을 해제합니다. 역할 관리하기 권한을 요구합니다.")
    @discord.default_permissions(manage_roles=True)
    async def Remove_Role_Member(self, ctx, Member: discord.Option(discord.Member, name="사용자", description="역할을 해제할 사용자를 지정하세요."),
        Role: discord.Option(discord.Role, name="역할", description="해제할 역할을 지정하세요."),
        Reason: discord.Option(str, name="사유", description="해제할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        await Control_Role(ctx, Member, Role, Reason, Remove=True)

    Channel_CMDGroup = Moderate_CMDGroup.create_subgroup("채널")

    Channel_Types = {
        "텍스트 채널": lambda g, n, c: g.create_text_channel(name=n, category=c),
        "음성 채널": lambda g, n, c: g.create_voice_channel(name=n, category=c),
        "스테이지 채널": lambda g, n, c: g.create_stage_channel(name=n, category=c),
        "카테고리": lambda g, n, c: g.create_category_channel(name=n),
        "포럼 채널": lambda g, n, c: g.create_forum_channel(name=n, category=c)
    }

    # /관리 채널 생성 [이름] [유형] [카테고리]
    @Channel_CMDGroup.command(name="생성", description="서버에 채널 또는 카테고리를 생성합니다. 채널 관리하기 권한을 요구합니다.")
    @discord.default_permissions(manage_channels=True)
    async def Create_Channel(self, ctx, Name: discord.Option(str, name="이름", description="생성할 채널의 이름을 입력하세요."),
        Type: discord.Option(str, name="유형", description="생성할 채널의 유형을 지정하세요. (선택)", choices=list(Channel_Types.keys()), default="텍스트 채널"),
        Category: discord.Option(discord.CategoryChannel, name="카테고리", description="채널을 생성할 카테고리를 지정하세요. (선택, 텍스트 / 음성 채널 전용)", required=False, default=None)):

        # 권한 확인
        if not ctx.author.guild_permissions.manage_channels:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 채널 관리하기 권한이 없습니다."), ephemeral=True)

        # 채널 생성 실행
        try:
            Channel = await Channel_Types[Type](ctx.guild, Name, Category)
            embed = discord.Embed(title=f"💬 새 채널을 생성했습니다.", color=discord.Color.green())
            embed.add_field(name="이름", value=Channel.name if Type == "카테고리" else Channel.mention, inline=True)
            embed.add_field(name="유형", value=Type, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{Type}을 생성했습니다.", ctx.guild.name, ctx.author.name, Name)
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 채널을 생성할 권한이 없습니다."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"채널 생성 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /관리 채널 삭제 [채널]
    @Channel_CMDGroup.command(name="삭제", description="서버의 채널을 삭제합니다. 채널 관리하기 권한을 요구합니다.")
    @discord.default_permissions(manage_channels=True)
    async def Delete_Channel(self, ctx, Channel: discord.Option(discord.abc.GuildChannel, name="채널", description="삭제할 채널을 지정하세요.", required=True),
        Reason: discord.Option(str, name="사유", description="채널을 삭제할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.manage_channels:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 채널 관리하기 권한이 없습니다."), ephemeral=True)

        # 채널 삭제 실행
        try:
            Channel_Name = Channel.name
            await Channel.delete(reason=f"{Reason} (요청자: {ctx.author.display_name})")
            embed = discord.Embed(title=f"🗑️ 채널을 삭제했습니다.", color=discord.Color.red())
            embed.add_field(name="이름", value=Channel_Name, inline=True)
            embed.add_field(name="사유", value=Reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", "채널을 삭제했습니다.", ctx.guild.name, ctx.author.name, Channel_Name)
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 채널을 삭제할 권한이 없습니다."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"채널 삭제 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    Message_CMDGroup = Moderate_CMDGroup.create_subgroup("메세지")

    # /관리 메세지 삭제 [개수] [채널]
    @Message_CMDGroup.command(name="삭제", description="지정한 개수만큼 메세지를 삭제합니다. 메세지 관리 권한, 전체 삭제는 관리자 권한을 요구합니다.")
    @discord.default_permissions(manage_messages=True)
    async def Purge_Messages(self, ctx, Amount: discord.Option(str, name="개수", description="삭제할 메세지의 개수를 입력하세요. (1 ~ 1000 또는 전체)"),
        Channel: discord.Option(discord.TextChannel, name="채널", description="메세지를 삭제할 채널을 지정하세요. (선택)", required=False, default=None)):

        # 권한 확인
        if not ctx.author.guild_permissions.manage_messages:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 메세지 관리 권한이 없습니다."), ephemeral=True)

        await ctx.defer(ephemeral=True)

        # 채널 미지정 시 현재 채널로 설정
        Target_Channel = Channel or ctx.channel

        try:
            # 메세지 전체 삭제 시 채널 복제 후 삭제
            if Amount == "전체":
                # 관리자 권한 확인
                if not ctx.author.guild_permissions.administrator:
                    return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 서버 관리자 권한이 없습니다."), ephemeral=True)

                # 채널 복제 및 삭제
                New_Channel = await Target_Channel.clone(reason=f"메세지 전체 삭제 (요청자: {ctx.author.display_name})")
                await Target_Channel.delete(reason=f"메세지 전체 삭제 (요청자: {ctx.author.display_name})")
                
                Deleted_Text = "전체"

                await New_Channel.send(
                    embed = discord.Embed(title=f"🗑️ 메세지를 삭제했습니다.", color=discord.Color.green())
                    .add_field(name="채널", value=New_Channel.mention, inline=True)
                    .add_field(name="삭제된 메세지", value=Deleted_Text, inline=True)
                    .add_field(name="요청자", value=ctx.author.display_name, inline=True)
                    .set_footer(text=f"일시: {Current_Time()}"), delete_after=5
                )
                
                # 요청한 채널과 삭제된 채널이 다른 경우 현재 채널에도 알림
                if Target_Channel.id != ctx.channel.id:
                    await ctx.followup.send(embed=Success_Dialog_Embed(f"{New_Channel.mention} 채널의 메세지를 모두 삭제했습니다."))
            else:
                Purge_Amount = int(Amount)

                if not 1 <= Purge_Amount <= 1000:
                    return await ctx.followup.send(embed=Error_Dialog_Embed("1에서 1000 사이 정수를 입력하세요."), ephemeral=True)

                Deleted = await Target_Channel.purge(limit=Purge_Amount)
                Deleted_Text = f"{len(Deleted)}개"
                
                await ctx.followup.send(
                    embed = discord.Embed(title=f"🗑️ 메세지를 삭제했습니다.", color=discord.Color.green())
                    .add_field(name="채널", value=Target_Channel.mention, inline=True)
                    .add_field(name="삭제된 메세지", value=Deleted_Text, inline=True)
                    .add_field(name="요청자", value=ctx.author.display_name, inline=True)
                    .set_footer(text=f"일시: {Current_Time()}")
                )

                Print_Log("Moderate", "메세지를 삭제했습니다.", ctx.guild.name, ctx.author.name, Target_Channel.name, f"삭제된 메세지: {Deleted_Text}")
        except ValueError:
            return await ctx.followup.send(embed=Error_Dialog_Embed("올바른 개수를 입력하세요."), ephemeral=True)
        except discord.Forbidden:
            await ctx.followup.send(embed=Error_Dialog_Embed("애플리케이션에게 메세지 관리 권한이 없습니다."), ephemeral=True)
        except Exception as e:
            await ctx.followup.send(embed=Error_Dialog_Embed(f"메세지 삭제 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    Warning_CMDGroup = Moderate_CMDGroup.create_subgroup("경고")

    # /관리 경고 부여 [@사용자] [횟수] [사유]
    @Warning_CMDGroup.command(name="부여", description="사용자에게 경고를 부여합니다. 멤버 관리 권한을 요구합니다.")
    @discord.default_permissions(moderate_members=True)
    async def Give_Warning_Member(self, ctx, Member: discord.Option(discord.Member, name="사용자", description="경고를 부여할 사용자를 지정하세요."),
        Amount: discord.Option(int, name="횟수", description="경고를 부여할 횟수를 입력하세요. (선택)", required=False, min_value=1, default=1),
        Reason: discord.Option(str, name="사유", description="경고를 부여할 사유를 입력하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.moderate_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 관리 권한이 없습니다."), ephemeral=True)

        if Member in [ctx.author] or Member.bot:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자가 스스로에게 경고를 부여할 수 없습니다."), ephemeral=True)

        # 경고 데이터 처리
        try:
            Warnings, User_Key, Data = self.Get_Warning_Data(ctx.guild.id, Member.id)
            
            Data["Count"] += Amount
            Data["Reasons"].append({
                "Reason": f"{Reason} ({Amount}회)" if Amount > 1 else Reason,
                "Issuer": ctx.author.display_name,
                "Time": Current_Time()
            })

            Save_Data(self.Warning_Data_Path, Warnings)

            embed = discord.Embed(title=f"⚠️ {Member.display_name}님에게 경고를 부여했습니다.", color=discord.Color.yellow())
            embed.add_field(name="부여한 경고", value=f"{Amount}회", inline=True)
            embed.add_field(name="현재 경고", value=f"{Data['Count']}회", inline=True)
            embed.add_field(name="사유", value=Reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=Member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", "경고를 부여했습니다.", ctx.guild.name, ctx.author.name, Member.name, Extra=f"부여 횟수: {Amount}회")
            await self.Run_Auto_Punish(ctx, Member, Data["Count"])
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"경고를 부여하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /관리 경고 목록 [@사용자]
    @Warning_CMDGroup.command(name="목록", description="사용자의 경고 목록을 표시합니다.")
    async def Check_Warning(self, ctx, Member: discord.Option(discord.Member, name="사용자", description="경고 목록을 표시할 사용자를 지정하세요. (선택)", required=False, default=None)):
        Target_Member = Member or ctx.author

        try:
            Warnings, _, Data = self.Get_Warning_Data(ctx.guild.id, Target_Member.id)

            if not Data["Reasons"]:
                return await ctx.respond(embed=Success_Dialog_Embed(f"{Target_Member.display_name}님의 경고가 없습니다."))

            View = Warning_Page_View(Target_Member, Data["Reasons"])
            Embed = View.Create_Embed()

            Embed.insert_field_at(0, name="누적 경고", value=f"{Data['Count']}회", inline=False)
            await ctx.respond(embed=Embed, view=View)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"경고 목록을 표시하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /관리 경고 제거 [@사용자] [횟수] [사유]
    @Warning_CMDGroup.command(name="제거", description="사용자의 경고를 제거합니다. 멤버 관리 권한을 요구합니다.")
    @discord.default_permissions(moderate_members=True)
    async def Remove_Warning(self, ctx, Member: discord.Option(discord.Member, name="사용자", description="경고를 제거할 사용자를 지정하세요."),
        Amount: discord.Option(str, name="횟수", description="제거할 경고 횟수를 입력하세요. (1 ~ 100 또는 전체)", default="1"),
        Reason: discord.Option(str, name="사유", description="경고를 제거할 사유를 입력하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.moderate_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 관리 권한이 없습니다."), ephemeral=True)

        try:
            Warnings, User_Key, Data = self.Get_Warning_Data(ctx.guild.id, Member.id)

            if Data["Count"] <= 0:
                return await ctx.respond(embed=Error_Dialog_Embed(f"{Member.display_name}님의 경고가 없습니다."), ephemeral=True)

            Remove_Amount = Data["Count"] if Amount == "전체" else int(Amount)

            if Remove_Amount <= 0:
                return await ctx.respond(embed=Error_Dialog_Embed("1 이상 100 이하의 정수를 입력하세요."), ephemeral=True)

            Remove_Amount = min(Remove_Amount, Data["Count"])

            Data["Count"] -= Remove_Amount

            if Data["Count"] == 0:
                Data["Reasons"] = []
            else:
                Data["Reasons"].append({"Reason": f"[경고 제거] {Reason}", "Issuer": ctx.author.display_name, "Time": Current_Time()})

            Save_Data(self.Warning_Data_Path, Warnings)

            embed = discord.Embed(title=f"✅ {Member.display_name}님의 경고를 제거했습니다.", color=discord.Color.green())
            embed.add_field(name="제거한 경고", value="전체 삭제" if Amount == "전체" else f"{Remove_Amount}회", inline=True)
            embed.add_field(name="현재 경고", value=f"{Data['Count']}회", inline=True)
            embed.add_field(name="사유", value=Reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=Member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", "경고를 제거했습니다.", ctx.guild.name, ctx.author.name, Member.name, Extra=f"제거한 경고 횟수: {Remove_Amount}회")
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"경고를 제거하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

def setup(bot):
    bot.add_cog(Moderate(bot))