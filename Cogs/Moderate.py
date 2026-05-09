import discord, re, datetime, asyncio, json, os
from Resources import Current_Time, Error_Dialog_Embed
from discord.ext import commands

def Parse_Duration(duration: str):
    Time_Pattern = {
        "년": 365 * 24 * 60 * 60,
        "개월": 30 * 24 * 60 * 60,
        "주": 7 * 24 * 60 * 60,
        "일": 24 * 60 * 60,
        "시간": 60 * 60,
        "분": 60,
        "초": 1
    }

    Total_Seconds = 0

    Matches = re.findall(r"(\d+)(년|개월|주|일|시간|분|초)", duration)

    if not Matches:
        return None

    for value, unit in Matches:
        Total_Seconds += int(value) * Time_Pattern[unit]

    return datetime.timedelta(seconds=Total_Seconds)

class Moderate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.Timeout_Data_Path = "Datas/Timeout_Data.json"
        self.Timeout_Tasks = {}
        
        # 애플리케이션이 실행되면 저장된 타임아웃 정보를 복원
        self.bot.loop.create_task(self.Restore_Timeouts())

    # 타임아웃 정보 저장 스크립트
    def Save_Timeouts(self, data):
        with open(self.Timeout_Data_Path, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

    # 타임아웃 정보 불러오기 스크립트
    def Load_Timeouts(self):
        if not os.path.exists(self.Timeout_Data_Path):
            return {}

        try:
            with open(self.Timeout_Data_Path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except:
            return {}

    # 애플리케이션 재시작 시 타임아웃 정보 불러오기 스크립트
    async def Restore_Timeouts(self):
        await self.bot.wait_until_ready()

        Timeouts = self.Load_Timeouts()

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
        
        self.Save_Timeouts(Timeouts)

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
            await member.kick(reason=reason)
            embed = discord.Embed(title=f"⚠️ {member.display_name}님을 서버에서 추방했습니다.", color=discord.Color.red())
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            print(f"[Moderate] 사용자를 추방했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 대상: {member.name})")
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
            await ctx.guild.ban(Target_User, reason=reason)
            embed = discord.Embed(title=f"🔨 {Target_User.display_name}님을 서버에서 차단했습니다.", color=discord.Color.red())
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=Target_User.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            print(f"[Moderate] 사용자를 차단했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 대상: {Target_User.name})")

            # 서버 멤버인 경우, 메세지 삭제를 선택한 경우 차단 대상 멤버가 전송한 모든 메세지 삭제
            if Guild_Member and delete_messages:
                for channel in ctx.guild.text_channels:
                    try:
                        Deleted = await channel.purge(limit=None, check=lambda message: message.author.id == Target_User.id, reason="멤버 차단으로 인한 메세지 삭제")
                        Deleted_Messages += len(Deleted)
                    except:
                        pass
                print(f"[Moderate] 메세지를 삭제했습니다. (서버: {ctx.guild.name}, 대상: {Target_User.name}, 삭제된 메세지: {Deleted_Messages}개)")
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
            print(f"[Moderate] 사용자의 차단을 해제했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 대상: {Target_User.name})")
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
                    print(f"[Moderate] 타임아웃을 자동으로 연장했습니다. (서버: {member.guild.name}, 대상: {member.name}, 남은 기간: {remaining_duration})")
                except discord.Forbidden:
                    print(f"[Moderate] 타임아웃 자동 연장에 실패했습니다. (권한 부족, 서버: {member.guild.name}, 대상: {member.name})")
                    break
        except asyncio.CancelledError:
            print(f"[Moderate] 타임아웃 자동 연장 작업이 취소되었습니다. (대상: {member.name})")
        except Exception as e:
            print(f"[Moderate] 타임아웃 자동 연장 중 오류 발생: {e}")
        finally:
            # 작업 종료 시 데이터베이스 및 태스크 관리 정리
            Timeouts = self.Load_Timeouts()
            if Task_Key in Timeouts and remaining_duration.total_seconds() <= 0:
                del Timeouts[Task_Key]
                self.Save_Timeouts(Timeouts)
            
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

            await member.timeout_for(Initial_Apply_Duration, reason=reason)

            # 기간이 28일 이상이면 데이터 저장 및 자동 연장 태스크 시작
            if Duration_Delta > Max_API_Limit:
                Timeouts = self.Load_Timeouts()
                Timeouts[Task_Key] = {
                    "Guild_ID": ctx.guild.id,
                    "Member_ID": member.id,
                    "Target_End": Final_End_Time.isoformat(),
                    "Reason": reason
                }
                self.Save_Timeouts(Timeouts)
                
                Remaining_Duration = Duration_Delta - Max_API_Limit
                Task = self.bot.loop.create_task(self.Auto_Extend_Timeout(member, Initial_Apply_Duration, Remaining_Duration, reason))
                self.Timeout_Tasks[Task_Key] = Task

            embed = discord.Embed(title=f"⚠️ {member.display_name}님을 타임아웃했습니다.", color=discord.Color.yellow())
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.add_field(name="기간", value=f"{Final_End_Time.strftime('%Y년 %m월 %d일 %H:%M:%S')}까지", inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            print(f"[Moderate] 사용자를 타임아웃했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 대상: {member.name}, 기간: {duration})")
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
            await member.timeout(None, reason=reason)
            
            # 자동 연장 데이터 및 태스크 삭제
            Task_Key = f"{ctx.guild.id}_{member.id}"
            if Task_Key in self.Timeout_Tasks:
                self.Timeout_Tasks[Task_Key].cancel()

            Timeouts = self.Load_Timeouts()
            if Task_Key in Timeouts:
                del Timeouts[Task_Key]
                self.Save_Timeouts(Timeouts)

            embed = discord.Embed(title=f"✅ {member.display_name}님의 타임아웃을 해제했습니다.", color=discord.Color.green())
            embed.add_field(name="사유", value=reason, inline=True)
            embed.add_field(name="요청자", value=ctx.author.display_name, inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"일시: {Current_Time()}")
            await ctx.respond(embed=embed)
            print(f"[Moderate] 사용자의 타임아웃을 해제했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 대상: {member.name})")
        # 애플리케이션 권한 예외 처리
        except discord.Forbidden:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션에게 해당 멤버의 타임아웃을 해제할 권한이 없습니다."), ephemeral=True)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"타임아웃 해제 중 오류가 발생했습니다. ({e})"), ephemeral=True)

def setup(bot):
    bot.add_cog(Moderate(bot))