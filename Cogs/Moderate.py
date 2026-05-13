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
        End = Start + self.Items_per_Page
        Current_Reasons = self.Reasons[Start:End]
        
        embed = discord.Embed(title=f"⚠️ {self.Target_Member.display_name}님의 경고 목록", color=discord.Color.yellow())
        
        if not Current_Reasons:
            embed.description = "표시할 경고 목록이 없습니다."
        else:
            for i, r in enumerate(Current_Reasons, Start + 1):
                embed.add_field(
                    name=f"{i}. {r['Reason']}",
                    value=f"요청자: {r['Issuer']} | 일시: {r['Time']}",
                    inline=False
                )
            
        embed.set_thumbnail(url=self.Target_Member.display_avatar.url)
        embed.set_footer(text=f"페이지 {self.Current_Page + 1}/{self.Max_Page + 1} | 일시: {Current_Time()}")
        return embed

    def Update_Buttons(self):
        # 버튼 활성화/비활성화 상태 갱신
        self.Prev_Button.disabled = self.Current_Page == 0
        self.Next_Button.disabled = self.Current_Page == self.Max_Page
        # 페이지가 1개뿐이면 버튼을 숨기거나 비활성화
        if self.Max_Page == 0:
            self.Prev_Button.disabled = True
            self.Next_Button.disabled = True

    @discord.ui.button(label="이전", style=discord.ButtonStyle.gray)
    async def Prev_Button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.Current_Page > 0:
            self.Current_Page -= 1
            self.Update_Buttons()
            await interaction.response.edit_message(embed=self.Create_Embed(), view=self)

    @discord.ui.button(label="다음", style=discord.ButtonStyle.gray)
    async def Next_Button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.Current_Page < self.Max_Page:
            self.Current_Page += 1
            self.Update_Buttons()
            await interaction.response.edit_message(embed=self.Create_Embed(), view=self)

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
        if message.author.bot or not message.guild:
            return
        
        # 권한 확인 (관리자는 제외)
        if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages:
            return

        # 설정 불러오기
        Settings = Load_Data(self.Settings_Data_Path)
        Guild_ID = str(message.guild.id)
        
        if Guild_ID not in Settings or "Anti_Spam" not in Settings[Guild_ID]:
            return
        
        Config = Settings[Guild_ID]["Anti_Spam"]
        if not Config.get("Enabled"):
            return
        
        Threshold_Count = Config["Count"]
        Threshold_Seconds = Config["Seconds"]
        Mode = Config.get("Mode", "모든 메시지")
        
        # 메시지 기록 업데이트
        Now = datetime.datetime.now().timestamp()
        User_Key = (message.guild.id, message.author.id)
        
        if User_Key not in self.Message_Cache:
            self.Message_Cache[User_Key] = []
        
        self.Message_Cache[User_Key].append((Now, message.content))
        
        # 시간 범위 밖의 메시지 기록 삭제
        self.Message_Cache[User_Key] = [item for item in self.Message_Cache[User_Key] if Now - item[0] <= Threshold_Seconds]
        
        # 도배 감지 조건 계산
        if Mode == "동일한 메시지":
            # 현재 메시지와 동일한 내용의 메시지만 카운트
            Relevant_Messages = [item for item in self.Message_Cache[User_Key] if item[1] == message.content]
            Spam_Count = len(Relevant_Messages)
            Is_Spam = Spam_Count >= Threshold_Count
            Reason_Text = f"동일한 내용 도배 ({Threshold_Seconds}초 내 {Spam_Count}회)"
        else:
            # 모든 메시지 카운트
            Spam_Count = len(self.Message_Cache[User_Key])
            Is_Spam = Spam_Count >= Threshold_Count
            Reason_Text = f"메시지 과다 전송 ({Threshold_Seconds}초 내 {Spam_Count}회)"

        # 도배 감지 시 처벌 부여
        if Is_Spam:
            # 기록 초기화 (중복 처벌 방지)
            del self.Message_Cache[User_Key]
            
            Action = Config["Action"]
            Duration_Str = Config.get("Duration")
            Punish_Reason = f"[자동 처벌] {Reason_Text}"
            
            try:
                if Action == "차단":
                    await message.author.ban(reason=Punish_Reason, delete_message_days=1)
                    Punish_Msg = f"도배 감지에 의해 **차단**했습니다."
                elif Action == "추방":
                    await message.author.kick(reason=Punish_Reason)
                    Punish_Msg = f"도배 감지에 의해 **추방**했습니다."
                elif Action == "타임아웃":
                    Duration_Delta = Parse_Duration(Duration_Str)
                    if Duration_Delta:
                        await message.author.timeout_for(Duration_Delta, reason=Punish_Reason)
                        Punish_Msg = f"도배 감지에 의해 **{Duration_Str}간 타임아웃**했습니다."
                    else:
                        return
                
                # 로그 출력
                await message.channel.send(embed=Success_Dialog_Embed(f"{message.author.display_name}님을 {Punish_Msg}"))
                Print_Log("Moderate", f"자동 처벌 ({Action})을 실행했습니다.", message.guild.name, "애플리케이션 (도배 감지)", message.author.name, extra=f"감지 사유: {Reason_Text}")
                
            except Exception as e:
                Print_Log("Moderate", "자동 처벌 중 오류가 발생했습니다.", message.guild.name, "애플리케이션 (도배 감지)", message.author.name, extra=f"오류: {e}")

    # 권한 부여 감지
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if not after.guild:
            return
        
        # 역할 부여 감지
        if len(before.roles) < len(after.roles):
            # 부여한 역할들 중 관리자 권한이 있는지 확인
            New_Roles = [role for role in after.roles if role not in before.roles]
            Admin_Roles = [role for role in New_Roles if role.permissions.administrator]
            
            if Admin_Roles:
                # 설정 불러오기
                Settings = Load_Data(self.Settings_Data_Path)
                Guild_ID = str(after.guild.id)
                
                if Guild_ID in Settings and Settings[Guild_ID].get("Anti_Admin", {}).get("Enabled"):
                    # 감사 로그 확인
                    try:
                        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
                            if entry.target.id == after.id:
                                Issuer = entry.user
                                
                                # 서버 소유자가 부여한 경우는 허용
                                if Issuer.id == after.guild.owner_id:
                                    return
                                
                                # 애플리케이션 자신이나 서버 소유자는 처리 대상에서 제외
                                if Issuer.id == self.bot.user.id:
                                    return

                                # 보안 조치: 역할 부여자와 대상자 모두 차단
                                Reason = f"[권한 부여 감지] 승인되지 않은 관리자 권한 부여 감지 (부여자: {Issuer.name})"
                                
                                # 대상자 차단
                                if not after.id == after.guild.owner_id:
                                    await after.ban(reason=Reason)
                                
                                # 부여자 차단
                                if not Issuer.id == after.guild.owner_id:
                                    await Issuer.ban(reason=Reason)
                                
                                Print_Log("Moderate", "사용자를 차단했습니다.", after.guild.name, "애플리케이션 (권한 부여 감지)", after.name, extra=f"부여자: {Issuer.name}")
                                break
                    except Exception as e:
                        Print_Log("Moderate", "사용자를 차단하는 중 오류가 발생했습니다.", after.guild.name, "애플리케이션 (권한 부여 감지)", after.name, extra=f"오류: {e}")

    # 레이드 감지 엔진
    async def Check_Channel_Raid(self, guild, action_type):
        # 설정 확인
        try:
            Settings = Load_Data(self.Settings_Data_Path)
            Guild_ID = str(guild.id)
            
            if Guild_ID not in Settings or "Anti_Channel" not in Settings[Guild_ID]:
                return
            
            Config = Settings[Guild_ID]["Anti_Channel"]
            if not Config.get("Enabled"):
                return
            
            Threshold_Count = Config["Count"]
            Threshold_Seconds = Config["Seconds"]
            
            # 감사 로그 확인 (최근 채널 작업 수행자 찾기)
            Audit_Action = discord.AuditLogAction.channel_create if action_type == "create" else discord.AuditLogAction.channel_delete
            
            async for entry in guild.audit_logs(limit=3, action=Audit_Action):
                # 애플리케이션 자신이나 소유자는 제외
                if entry.user.id == self.bot.user.id or entry.user.id == guild.owner_id:
                    continue
                
                Issuer = entry.user
                Now = datetime.datetime.now().timestamp()
                User_Key = (guild.id, Issuer.id)
                
                if User_Key not in self.Channel_Cache:
                    self.Channel_Cache[User_Key] = []
                
                self.Channel_Cache[User_Key].append(Now)
                
                # 시간 범위 밖의 기록 삭제
                self.Channel_Cache[User_Key] = [ts for ts in self.Channel_Cache[User_Key] if Now - ts <= Threshold_Seconds]
                
                # 레이드 감지
                if len(self.Channel_Cache[User_Key]) >= Threshold_Count:
                    # 기록 초기화
                    del self.Channel_Cache[User_Key]
                    
                    Reason = f"[레이드 감지] 지정한 시간 내 다발적 채널 {'생성' if action_type == 'create' else '삭제'} 감지 ({Threshold_Seconds}초 내 {Threshold_Count}회 이상)"
                    
                    # 시도자 차단
                    await Issuer.ban(reason=Reason)
                    
                    Print_Log("Moderate", "사용자를 차단했습니다.", guild.name, "애플리케이션 (레이드 감지)", Issuer.name, extra=f"작업: 채널 {action_type}")
                    break
        except Exception as e:
            Print_Log("Moderate", "사용자를 차단하는 중 오류가 발생했습니다.", guild.name, "애플리케이션 (레이드 감지)", extra=f"오류: {e}")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await self.Check_Channel_Raid(channel.guild, "create")

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

        for Key, Info in list(Timeouts.items()):
            Guild = self.bot.get_guild(Info.get('Guild_ID'))
            if not Guild: continue
            
            Member = Guild.get_member(Info.get('Member_ID'))
            if not Member: continue

            # 남은 전체 기간 계산
            Target_End = datetime.datetime.fromisoformat(Info.get('Target_End'))

            if Target_End.tzinfo is None:
                Target_End = Target_End.replace(tzinfo=datetime.timezone.utc)
            
            Remaining = Target_End - discord.utils.utcnow()

            if Remaining.total_seconds() <= 0:
                del Timeouts[Key]
                continue

            # 멤버의 타임아웃 잔여 기간 계산
            if Member.communication_disabled_until:
                Applied_Remaining = Member.communication_disabled_until - discord.utils.utcnow()
                
                # 기존 태스크가 있다면 취소
                Task_Key = f"{Guild.id}_{Member.id}"
                if Task_Key in self.Timeout_Tasks:
                    self.Timeout_Tasks[Task_Key].cancel()

                # 백그라운드 태스크 재시작
                Task = self.bot.loop.create_task(self.Auto_Extend_Timeout(Member, Applied_Remaining, Remaining, Info.get('Reason', '사유 없음')))
                self.Timeout_Tasks[Task_Key] = Task
            else:
                # 타임아웃이 해제되어 있으면 키 제거
                del Timeouts[Key]
        
        Save_Data(self.Timeout_Data_Path, Timeouts)

    Moderate_CMDGroup = discord.SlashCommandGroup("관리")

    # /관리 추방 [@사용자] [사유]
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
            await member.kick(reason=f"{reason} (요청자: {ctx.author.display_name})")
            embed = discord.Embed(title=f"⚠️ {member.display_name}님을 서버에서 추방했습니다.", color=discord.Color.red())
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{member.display_name}님을 추방했습니다.", ctx.guild.name, ctx.author.name, member.name)
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
        user: discord.Option(str, name="사용자", description="차단할 사용자의 멘션 또는 사용자 ID를 입력하세요."),
        reason: discord.Option(str, name="사유", description="차단할 사유를 지정하세요. (선택)", required=False, default="사유 없음"),
        delete_messages: discord.Option(bool, name="메세지", description="차단할 사용자의 모든 메세지를 삭제합니다. (선택)", required=False, default=False)):

        # 요청자 권한 확인
        if not ctx.author.guild_permissions.ban_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 차단하기 권한이 없습니다."), ephemeral=True)

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

        # 서버 멤버 여부 확인
        Guild_Member = ctx.guild.get_member(User_ID)
        Deleted_Messages = 0

        # 차단 실행
        try:
            await ctx.guild.ban(Target_User, reason=f"{reason} (요청자: {ctx.author.display_name})")
            embed = discord.Embed(title=f"⚒️ {Target_User.display_name}님을 서버에서 차단했습니다.", color=discord.Color.red())
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=Target_User.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{Target_User.display_name}님을 차단했습니다.", ctx.guild.name, ctx.author.name, Target_User.name)

            # 서버 멤버인 경우, 메세지 삭제를 선택한 경우 차단 대상 멤버가 전송한 모든 메세지 삭제
            if Guild_Member and delete_messages:
                for channel in ctx.guild.text_channels:
                    try:
                        Deleted = await channel.purge(limit=None, check=lambda message: message.author.id == Target_User.id, reason="멤버 차단으로 인한 메세지 삭제")
                        Deleted_Messages += len(Deleted)
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

        # 요청자 권한 확인
        if not ctx.author.guild_permissions.ban_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 차단하기 권한이 없습니다."), ephemeral=True)

        # 사용자 입력 값 처리
        User_ID_Match = re.search(r'\d+', user)
        if not User_ID_Match:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자를 찾을 수 없습니다. 올바른 사용자 멘션 또는 ID를 입력해주세요."), ephemeral=True)
        User_ID = int(User_ID_Match.group())

        Target_User = await self.bot.fetch_user(User_ID)

        # 차단 해제 실행
        try:
            await ctx.guild.unban(Target_User, reason=reason)
            embed = discord.Embed(title=f"✅ {Target_User.display_name}님의 차단을 해제했습니다.", color=discord.Color.green())
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=Target_User.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{Target_User.name}님의 차단을 해제했습니다.", ctx.guild.name, ctx.author.name, Target_User.name)
        except discord.NotFound:
            await ctx.respond(embed=Error_Dialog_Embed("이미 차단 해제된 사용자입니다."), ephemeral=True)
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 사용자의 차단을 해제할 권한이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"차단 해제 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    Timeout_CMDGroup = Moderate_CMDGroup.create_subgroup("타임아웃")

    # 타임아웃 자동 연장 스크립트
    async def Auto_Extend_Timeout(self, member: discord.Member, applied_duration: datetime.timedelta, remaining_duration: datetime.timedelta, reason: str):
        Task_Key = f"{member.guild.id}_{member.id}"
        try:
            while remaining_duration.total_seconds() > 0:
                # 현재 적용된 타임아웃이 종료되기 10초 전까지 대기
                Wait_Seconds = applied_duration.total_seconds() - 10
                if Wait_Seconds > 0:
                    await asyncio.sleep(Wait_Seconds)

                # 정확한 대기를 위해 멤버 객체 갱신 및 재확인
                member = await member.guild.fetch_member(member.id)
                if not member or not member.is_timed_out():
                    break

                # 다음 연장 기간 계산 (최대 28일)
                Next_Apply = min(remaining_duration, datetime.timedelta(days=28))
                
                try:
                    await member.timeout(Next_Apply, reason=f"[자동 연장] {reason}")
                    remaining_duration -= Next_Apply
                    applied_duration = Next_Apply
                    Print_Log("Moderate", "타임아웃을 자동으로 연장했습니다.", member.guild.name, "시스템 (자동 연장)", member.name, f"남은 기간: {remaining_duration}")
                except discord.Forbidden:
                    Print_Log("Moderate", "타임아웃 자동 연장에 실패했습니다.", member.guild.name, "시스템 (자동 연장)", member.name, "사유: 권한 부족")
                    break
        except asyncio.CancelledError:
            Print_Log("Moderate", "타임아웃 자동 연장 작업이 취소되었습니다.", member.guild.name, "시스템 (자동 연장)", member.name)
        except Exception as e:
            Print_Log("Moderate", "타임아웃 자동 연장 중 오류가 발생했습니다.", member.guild.name, "시스템 (자동 연장)", member.name, f"오류: {e}")
        finally:
            # 작업 종료 시 데이터베이스 및 태스크 관리 정리
            Timeouts = Load_Data(self.Timeout_Data_Path)
            if Task_Key in Timeouts and remaining_duration.total_seconds() <= 0:
                del Timeouts[Task_Key]
                Save_Data(self.Timeout_Data_Path, Timeouts)
            
            if Task_Key in self.Timeout_Tasks:
                del self.Timeout_Tasks[Task_Key]

    # /관리 타임아웃 부여 [@사용자] [기간] [사유]
    @Timeout_CMDGroup.command(name="부여", description="사용자를 타임아웃합니다. 타임아웃 멤버 권한을 요구합니다.")
    @discord.default_permissions(moderate_members=True)
    async def Timeout_Member(self, ctx, member: discord.Option(discord.Member, name="사용자", description="타임아웃할 사용자를 지정하세요."),
        duration: discord.Option(str, name="기간", description="타임아웃할 기간을 입력하세요. (ex: 10초, 3분, 1시간, 1일, 1주, 1개월, 1년)"),
        reason: discord.Option(str, name="사유", description="타임아웃할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.moderate_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 타임아웃 권한이 없습니다."), ephemeral=True)

        if member == ctx.author:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자가 스스로를 타임아웃할 수 없습니다."), ephemeral=True)

        if member == self.bot.user:
            return await ctx.respond(embed=Error_Dialog_Embed("애플리케이션을 타임아웃할 수 없습니다."), ephemeral=True)

        # 타임아웃 기간 파싱
        Duration_Delta = Parse_Duration(duration)
        if not Duration_Delta:
            return await ctx.respond(embed=Error_Dialog_Embed("올바른 기간 형식을 입력해주세요. (ex: 10초, 3분, 1시간, 1일, 1주, 1개월, 1년)"), ephemeral=True)

        # 타임아웃 종료 시점 계산 (datetime 객체)
        Final_End_Time = discord.utils.utcnow() + Duration_Delta
        Task_Key = f"{ctx.guild.id}_{member.id}"

        # 타임아웃 실행
        try:
            Max_API_Limit = datetime.timedelta(days=28)
            Initial_Apply_Duration = min(Duration_Delta, Max_API_Limit)

            # 기존 연장 태스크가 있다면 취소
            if Task_Key in self.Timeout_Tasks:
                self.Timeout_Tasks[Task_Key].cancel()

            await member.timeout_for(Initial_Apply_Duration, reason=f"{reason} (요청자: {ctx.author.display_name})")

            # 기간이 28일 이상이면 데이터 저장 및 자동 연장 태스크 시작
            if Duration_Delta > Max_API_Limit:
                Timeouts = Load_Data(self.Timeout_Data_Path)
                Timeouts[Task_Key] = {
                    "Guild_ID": ctx.guild.id,
                    "Member_ID": member.id,
                    "Target_End": Final_End_Time.isoformat(),
                    "Reason": reason
                }
                Save_Data(self.Timeout_Data_Path, Timeouts)
                
                Remaining_Duration = Duration_Delta - Max_API_Limit
                Task = self.bot.loop.create_task(self.Auto_Extend_Timeout(member, Initial_Apply_Duration, Remaining_Duration, reason))
                self.Timeout_Tasks[Task_Key] = Task

            embed = discord.Embed(title=f"🔇 {member.display_name}님을 타임아웃했습니다.", color=discord.Color.yellow())
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.add_field(name="기간", value=f"{Final_End_Time.strftime('%Y년 %m월 %d일 %H:%M:%S')}까지", inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{member.display_name}님을 타임아웃했습니다.", ctx.guild.name, ctx.author.name, member.name, f"기간: {Final_End_Time.strftime('%Y년 %m월 %d일 %H:%M:%S')}까지")
        # 애플리케이션 권한 예외 처리
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 멤버를 타임아웃할 권한이 없습니다. 서버 소유자 또는 관리자에게 문의해주세요."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"타임아웃 부여 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /관리 타임아웃 해제 [@사용자] [사유]
    @Timeout_CMDGroup.command(name="해제", description="사용자의 타임아웃을 해제합니다. 타임아웃 멤버 권한을 요구합니다.")
    @discord.default_permissions(moderate_members=True)
    async def Untimeout_Member(self, ctx, member: discord.Option(discord.Member, name="사용자", description="타임아웃을 해제할 사용자를 지정하세요."),
        reason: discord.Option(str, name="사유", description="타임아웃을 해제할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.moderate_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 타임아웃 권한이 없습니다."), ephemeral=True)

        if not member.timed_out:
            return await ctx.respond(embed=Error_Dialog_Embed("이미 타임아웃 상태가 아닌 사용자입니다."), ephemeral=True)

        # 타임아웃 해제 실행
        try:
            await member.timeout(None, reason=f"{reason} (요청자: {ctx.author.display_name})")
            
            # 자동 연장 데이터 및 태스크 삭제
            Task_Key = f"{ctx.guild.id}_{member.id}"
            if Task_Key in self.Timeout_Tasks:
                self.Timeout_Tasks[Task_Key].cancel()

            Timeouts = Load_Data(self.Timeout_Data_Path)
            if Task_Key in Timeouts:
                del Timeouts[Task_Key]
                Save_Data(self.Timeout_Data_Path, Timeouts)

            embed = discord.Embed(title=f"🔊 {member.display_name}님의 타임아웃을 해제했습니다.", color=discord.Color.green())
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{member.display_name}님의 타임아웃을 해제했습니다.", ctx.guild.name, ctx.author.name, member.name)
        # 애플리케이션 권한 예외 처리
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 멤버의 타임아웃을 해제할 권한이 없습니다."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"타임아웃 해제 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    Role_CMDGroup = Moderate_CMDGroup.create_subgroup("역할")

    # /관리 역할 부여 [@사용자] [@역할] [사유]
    @Role_CMDGroup.command(name="부여", description="사용자에게 역할을 부여합니다. 역할 관리하기 권한을 요구합니다.")
    @discord.default_permissions(manage_roles=True)
    async def Give_Role_Member(self, ctx,
        member: discord.Option(discord.Member, name="사용자", description="역할을 부여할 사용자를 지정하세요."),
        role: discord.Option(discord.Role, name="역할", description="부여할 역할을 지정하세요."),
        reason: discord.Option(str, name="사유", description="부여할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.manage_roles:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 역할 관리하기 권한이 없습니다."), ephemeral=True)

        if ctx.author.id != ctx.guild.owner_id and role.position >= ctx.author.top_role.position:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자 본인의 최상위 역할보다 높거나 같은 역할은 부여할 수 없습니다."), ephemeral=True)

        if role.position >= ctx.guild.me.top_role.position:
            return await ctx.respond(embed=Error_Dialog_Embed("애플리케이션의 최상위 역할보다 높거나 같은 역할은 부여할 수 없습니다."), ephemeral=True)

        # 역할 부여 실행
        try:
            if role in member.roles:
                return await ctx.respond(embed=Error_Dialog_Embed("이미 해당 역할을 보유하고 있는 사용자입니다."), ephemeral=True)
            
            await member.add_roles(role, reason=f"{reason} (요청자: {ctx.author.display_name})")
            embed = discord.Embed(title=f"👤 {member.display_name}님에게 역할을 부여했습니다.", color=role.color if role.color.value != 0 else discord.Color.blue())
            embed.add_field(name="역할", value=role.mention, inline=True)
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{member.display_name}님에게 역할을 부여했습니다.", ctx.guild.name, ctx.author.name, member.name, f"역할: {role.name}")
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 역할을 부여할 권한이 없습니다."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"역할 부여 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /관리 역할 해제 [@사용자] [@역할] [사유]
    @Role_CMDGroup.command(name="해제", description="사용자의 역할을 해제합니다. 역할 관리하기 권한을 요구합니다.")
    @discord.default_permissions(manage_roles=True)
    async def Remove_Role_Member(self, ctx,
        member: discord.Option(discord.Member, name="사용자", description="역할을 해제할 사용자를 지정하세요."),
        role: discord.Option(discord.Role, name="역할", description="해제할 역할을 지정하세요."),
        reason: discord.Option(str, name="사유", description="해제할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.manage_roles:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 역할 관리하기 권한이 없습니다."), ephemeral=True)

        if ctx.author.id != ctx.guild.owner_id and role.position >= ctx.author.top_role.position:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자 본인의 최상위 역할보다 높거나 같은 역할은 해제할 수 없습니다."), ephemeral=True)

        if role.position >= ctx.guild.me.top_role.position:
            return await ctx.respond(embed=Error_Dialog_Embed("애플리케이션의 최상위 역할보다 높거나 같은 역할은 해제할 수 없습니다."), ephemeral=True)

        # 역할 해제 실행
        try:
            if role not in member.roles:
                return await ctx.respond(embed=Error_Dialog_Embed("이미 해당 역할을 보유하고 있지 않은 사용자입니다."), ephemeral=True)
            
            await member.remove_roles(role, reason=f"{reason} (요청자: {ctx.author.display_name})")
            embed = discord.Embed(title=f"👤 {member.display_name}님의 역할을 해제했습니다.", color=discord.Color.yellow())
            embed.add_field(name="역할", value=role.mention, inline=True)
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{member.display_name}님의 역할을 해제했습니다.", ctx.guild.name, ctx.author.name, member.name, f"역할: {role.name}")
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 역할을 해제할 권한이 없습니다."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"역할 해제 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    Channel_CMDGroup = Moderate_CMDGroup.create_subgroup("채널")

    # /관리 채널 생성 [이름] [유형] [카테고리]
    @Channel_CMDGroup.command(name="생성", description="서버에 채널 또는 카테고리를 생성합니다. 채널 관리하기 권한을 요구합니다.")
    @discord.default_permissions(manage_channels=True)
    async def Create_Channel(self, ctx,
        name: discord.Option(str, name="이름", description="생성할 채널의 이름을 입력하세요."),
        type: discord.Option(str, name="유형", description="생성할 채널의 유형을 지정하세요. (선택)", choices=["텍스트 채널", "음성 채널", "스테이지 채널", "카테고리", "포럼 채널"], default="텍스트 채널"),
        category: discord.Option(discord.CategoryChannel, name="카테고리", description="채널을 생성할 카테고리를 지정하세요. (선택, 텍스트 / 음성 채널 전용)", required=False, default=None)):

        # 권한 확인
        if not ctx.author.guild_permissions.manage_channels:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 채널 관리하기 권한이 없습니다."), ephemeral=True)

        # 채널 생성 실행
        try:
            Created_Channel = None
            if type == "텍스트 채널":
                Created_Channel = await ctx.guild.create_text_channel(name=name, category=category)
            elif type == "음성 채널":
                Created_Channel = await ctx.guild.create_voice_channel(name=name, category=category)
            elif type == "스테이지 채널":
                Created_Channel = await ctx.guild.create_stage_channel(name=name, category=category)
            elif type == "카테고리":
                Created_Channel = await ctx.guild.create_category(name=name)
            elif type == "포럼 채널":
                Created_Channel = await ctx.guild.create_forum_channel(name=name, category=category)

            embed = discord.Embed(title=f"💬 새 채널을 생성했습니다.", color=discord.Color.green())
            embed.add_field(name="이름", value=Created_Channel.name if type == "카테고리" else Created_Channel.mention, inline=True)
            embed.add_field(name="유형", value=type, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            Print_Log("Moderate", f"{type}을 생성했습니다.", ctx.guild.name, ctx.author.name, name)
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 채널을 생성할 권한이 없습니다."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"채널 생성 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /관리 채널 삭제 [채널]
    @Channel_CMDGroup.command(name="삭제", description="서버의 채널을 삭제합니다. 채널 관리하기 권한을 요구합니다.")
    @discord.default_permissions(manage_channels=True)
    async def Delete_Channel(self, ctx,
        channel: discord.Option(discord.abc.GuildChannel, name="채널", description="삭제할 채널을 지정하세요.", required=True),
        reason: discord.Option(str, name="사유", description="채널을 삭제할 사유를 지정하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.manage_channels:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 채널 관리하기 권한이 없습니다."), ephemeral=True)

        # 채널 삭제 실행
        try:
            Channel_Name = channel.name
            await channel.delete(reason=f"{reason} (요청자: {ctx.author.display_name})")
            
            embed = discord.Embed(title=f"🗑️ 채널을 삭제했습니다.", color=discord.Color.red())
            embed.add_field(name="이름", value=Channel_Name, inline=True)
            embed.add_field(name="사유", value=reason, inline=True)
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
    async def Purge_Messages(self, ctx,
        amount: discord.Option(str, name="개수", description="삭제할 메세지의 개수를 입력하세요. (1 ~ 1000 또는 전체)"),
        channel: discord.Option(discord.TextChannel, name="채널", description="메세지를 삭제할 채널을 지정하세요. (선택)", required=False, default=None)):

        # 채널 미지정 시 현재 채널로 설정
        Target_Channel = channel or ctx.channel

        # 권한 확인
        if not ctx.author.guild_permissions.manage_messages:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 메세지 관리 권한이 없습니다."), ephemeral=True)

        await ctx.defer(ephemeral=True)

        # 메세지 전체 삭제 시 채널 복제 후 삭제
        if amount == "전체":
            # 관리자 권한 확인
            if not ctx.author.guild_permissions.administrator:
                return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 서버 관리자 권한이 없습니다."), ephemeral=True)

            try:
                # 채널 정보 저장
                Channel_Name = Target_Channel.name
                
                # 채널 복제 및 삭제
                New_Channel = await Target_Channel.clone(reason=f"메세지 전체 삭제 (요청자: {ctx.author.display_name})")
                await Target_Channel.delete(reason=f"메세지 전체 삭제 (요청자: {ctx.author.display_name})")
                
                embed = discord.Embed(title=f"🗑️ 메세지를 삭제했습니다.", color=discord.Color.green())
                embed.add_field(name="채널", value=New_Channel.mention, inline=True)
                embed.add_field(name="삭제된 메세지", value="전체", inline=True)
                embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
                embed.set_footer(text=f"일시: {Current_Time()}")
                
                # 복제된 채널에 알림 전송
                await New_Channel.send(embed=embed, delete_after=5)
                
                # 요청한 채널과 삭제된 채널이 다른 경우 현재 채널에도 알림
                if Target_Channel.id != ctx.channel.id:
                    await ctx.followup.send(embed=embed)
                
                Print_Log("Moderate", "메세지를 삭제했습니다.", ctx.guild.name, ctx.author.name, Channel_Name, "삭제된 메세지: 전체")
                return
            except discord.Forbidden:
                return await ctx.followup.send(embed=Error_Dialog_Embed("애플리케이션에게 채널 관리 권한이 없습니다."), ephemeral=True)
            except Exception as e:
                return await ctx.followup.send(embed=Error_Dialog_Embed(f"메세지 전체 삭제 중 오류가 발생했습니다. ({e})"), ephemeral=True)

        # 개수 입력 시 숫자 파싱
        try:
            Purge_Amount = int(amount)
            if not 1 <= Purge_Amount <= 1000:
                return await ctx.followup.send(embed=Error_Dialog_Embed("1에서 1000 사이 정수를 입력하세요."), ephemeral=True)
        except ValueError:
            return await ctx.followup.send(embed=Error_Dialog_Embed("올바른 개수를 입력하거나 '전체'를 입력하세요."), ephemeral=True)

        # 메세지 삭제 실행
        try:
            Deleted = await Target_Channel.purge(limit=Purge_Amount)
            
            embed = discord.Embed(title=f"🗑️ 메세지를 삭제했습니다.", color=discord.Color.green())
            embed.add_field(name="채널", value=Target_Channel.mention, inline=True)
            embed.add_field(name="삭제된 메세지", value=f"{len(Deleted)}개", inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_footer(text=f"일시: {Current_Time()}")
            
            await ctx.followup.send(embed=embed)
            
            Print_Log("Moderate", "메세지를 삭제했습니다.", ctx.guild.name, ctx.author.name, Target_Channel.name, f"삭제된 메세지: {len(Deleted)}개")
        except discord.Forbidden:
            await ctx.followup.send(embed=Error_Dialog_Embed("애플리케이션에게 메세지 관리 권한이 없습니다."), ephemeral=True)
        except Exception as e:
            await ctx.followup.send(embed=Error_Dialog_Embed(f"메세지 삭제 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    Warning_CMDGroup = Moderate_CMDGroup.create_subgroup("경고")

    # /관리 경고 부여 [@사용자] [횟수] [사유]
    @Warning_CMDGroup.command(name="부여", description="사용자에게 경고를 부여합니다. 멤버 관리 권한을 요구합니다.")
    @discord.default_permissions(moderate_members=True)
    async def Give_Warning_Member(self, ctx,
        member: discord.Option(discord.Member, name="사용자", description="경고를 부여할 사용자를 지정하세요."),
        amount: discord.Option(int, name="횟수", description="경고를 부여할 횟수를 입력하세요. (선택)", required=False, min_value=1, default=1),
        reason: discord.Option(str, name="사유", description="경고를 부여할 사유를 입력하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.moderate_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 관리 권한이 없습니다."), ephemeral=True)

        if member == ctx.author:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자가 스스로에게 경고를 부여할 수 없습니다."), ephemeral=True)

        if member.bot:
            return await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 경고를 부여할 수 없습니다."), ephemeral=True)

        # 경고 데이터 처리
        try:
            Warnings = Load_Data(self.Warning_Data_Path)
            User_Key = f"{ctx.guild.id}_{member.id}"
            
            if User_Key not in Warnings:
                Warnings[User_Key] = {"Count": 0, "Reasons": []}
            
            Warnings[User_Key]["Count"] += amount
            Warnings[User_Key]["Reasons"].append({
                "Reason": f"{reason} ({amount}회 동시 부여)" if amount > 1 else reason,
                "Issuer": ctx.author.display_name,
                "Time": Current_Time()
            })
            
            Save_Data(self.Warning_Data_Path, Warnings)
            
            embed = discord.Embed(title=f"⚠️ {member.display_name}님에게 경고를 부여했습니다.", color=discord.Color.yellow())
            embed.add_field(name="부여한 경고 횟수", value=f"{amount}회", inline=True)
            embed.add_field(name="현재 경고 수", value=f"{Warnings[User_Key]['Count']}회", inline=True)
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            
            await ctx.respond(embed=embed)
            Print_Log("Moderate", "경고를 부여했습니다.", ctx.guild.name, ctx.author.name, member.name, f"부여한 횟수: {amount}회")

            # 자동 처벌 확인
            try:
                Settings = Load_Data(self.Settings_Data_Path)
                Guild_ID = str(ctx.guild.id)
                
                if Guild_ID in Settings and "Auto_Punish" in Settings[Guild_ID]:
                    Punish_Config = Settings[Guild_ID]["Auto_Punish"]
                    
                    if Punish_Config.get("Enabled") and Warnings[User_Key]["Count"] >= Punish_Config["Count"]:
                        Threshold = Punish_Config["Count"]
                        Action = Punish_Config["Action"]
                        Duration_Str = Punish_Config.get("Duration")
                        Punish_Reason = f"[자동 처벌] 경고 {Threshold}회 누적 (현재: {Warnings[User_Key]['Count']}회)"
                        
                        if Action == "차단":
                            await member.ban(reason=Punish_Reason, delete_message_days=0)
                            Punish_Msg = f"경고 누적에 의해 **차단**했습니다."
                        elif Action == "추방":
                            await member.kick(reason=Punish_Reason)
                            Punish_Msg = f"경고 누적에 의해 **추방**했습니다."
                        elif Action == "타임아웃":
                            Duration_Delta = Parse_Duration(Duration_Str)
                            if Duration_Delta:
                                await member.timeout_for(Duration_Delta, reason=Punish_Reason)
                                Punish_Msg = f"경고 누적에 의해 **{Duration_Str}간 타임아웃**했습니다."
                            else:
                                Punish_Msg = None # 기간 파싱 실패 시 처리 안 함
                        
                        if Punish_Msg:
                            await ctx.send(embed=Success_Dialog_Embed(f"{member.display_name}님을 {Punish_Msg}"))
                            Print_Log("Moderate", f"자동 처벌 ({Action})을 실행했습니다.", ctx.guild.name, "애플리케이션 (자동 처벌)", member.name, extra=f"현재 경고 횟수: {Warnings[User_Key]['Count']}회")
            except Exception as punish_error:
                Print_Log("Moderate", "자동 처벌 실행 중 오류가 발생했습니다.", ctx.guild.name, "애플리케이션 (자동 처벌)", member.name, extra=f"오류: {punish_error}")
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"경고 부여 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /관리 경고 목록 [@사용자]
    @Warning_CMDGroup.command(name="목록", description="사용자의 경고 목록을 표시합니다.")
    async def Check_Warning(self, ctx,
        member: discord.Option(discord.Member, name="사용자", description="경고 목록을 표시할 사용자를 지정하세요. (선택)", required=False, default=None)):

        Target_Member = member or ctx.author
        
        try:
            Warnings = Load_Data(self.Warning_Data_Path)
            User_Key = f"{ctx.guild.id}_{Target_Member.id}"
            
            if User_Key not in Warnings or not Warnings[User_Key]["Reasons"]:
                embed = Success_Dialog_Embed(f"{Target_Member.display_name}님이 받은 경고가 없습니다.")
                return await ctx.respond(embed=embed)

            Count = Warnings[User_Key]["Count"]
            Reasons = Warnings[User_Key]["Reasons"]
            
            # 페이지 뷰 생성
            View = Warning_Page_View(Target_Member, Reasons)
            Embed = View.Create_Embed()
            Embed.insert_field_at(0, name="누적 경고", value=f"{Count}회", inline=False)
            
            await ctx.respond(embed=Embed, view=View)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"경고 목록 조회 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /관리 경고 제거 [@사용자] [횟수] [사유]
    @Warning_CMDGroup.command(name="제거", description="사용자의 경고를 제거합니다. 멤버 관리 권한을 요구합니다.")
    @discord.default_permissions(moderate_members=True)
    async def Remove_Warning(self, ctx,
        member: discord.Option(discord.Member, name="사용자", description="경고를 제거할 사용자를 지정하세요."),
        amount: discord.Option(str, name="횟수", description="제거할 경고 횟수를 입력하세요. (1 ~ 100 또는 전체)", default="1"),
        reason: discord.Option(str, name="사유", description="경고를 제거할 사유를 입력하세요. (선택)", required=False, default="사유 없음")):

        # 권한 확인
        if not ctx.author.guild_permissions.moderate_members:
            return await ctx.respond(embed=Error_Dialog_Embed("사용자에게 멤버 관리 권한이 없습니다."), ephemeral=True)

        try:
            Warnings = Load_Data(self.Warning_Data_Path)
            User_Key = f"{ctx.guild.id}_{member.id}"
            
            if User_Key not in Warnings or Warnings[User_Key]["Count"] == 0:
                return await ctx.respond(embed=Error_Dialog_Embed(f"{member.display_name}님이 받은 경고가 없습니다."), ephemeral=True)
            
            Current_Count = Warnings[User_Key]["Count"]
            
            # 제거 횟수 처리
            if amount == "전체":
                Remove_Amount = Current_Count
            else:
                try:
                    Remove_Amount = int(amount)
                    if Remove_Amount <= 0:
                        return await ctx.respond(embed=Error_Dialog_Embed("1 이상 정수를 입력하세요."), ephemeral=True)
                    Remove_Amount = min(Current_Count, Remove_Amount)
                except ValueError:
                    return await ctx.respond(embed=Error_Dialog_Embed("올바른 횟수를 입력하거나 '전체'를 입력하세요."), ephemeral=True)
            
            Warnings[User_Key]["Count"] -= Remove_Amount
            
            # 전체 삭제인 경우 내역도 정리할지 선택 (여기선 0이 되면 내역도 비움)
            if Warnings[User_Key]["Count"] == 0:
                Warnings[User_Key]["Reasons"] = []
            else:
                # 제거 사유 기록
                Warnings[User_Key]["Reasons"].append({
                    "Reason": f"[경고 제거] {reason}",
                    "Issuer": ctx.author.display_name,
                    "Time": Current_Time()
                })
            
            Save_Data(self.Warning_Data_Path, Warnings)
            
            embed = discord.Embed(title=f"✅ {member.display_name}님의 경고를 제거했습니다.", color=discord.Color.green())
            embed.add_field(name="제거한 경고 횟수", value=f"{Remove_Amount}회" if amount != "전체" else "전체 삭제", inline=True)
            embed.add_field(name="현재 경고 횟수", value=f"{Warnings[User_Key]['Count']}회", inline=True)
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            
            await ctx.respond(embed=embed)
            Print_Log("Moderate", "경고를 제거했습니다.", ctx.guild.name, ctx.author.name, member.name, f"제거한 횟수: {Remove_Amount}회" if amount != "전체" else "전체 삭제")
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"경고 제거 중 오류가 발생했습니다. ({e})"), ephemeral=True)

def setup(bot):
    bot.add_cog(Moderate(bot))