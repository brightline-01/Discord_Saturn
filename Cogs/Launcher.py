import discord, os, shutil, atexit
from discord.ext import commands, tasks
from Config import APP_NAME, APP_VER, DEBUG_GUILD

# 애플리케이션과 연결 및 Presence 변경을 담당하는 Cog
class Launcher(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.Status_Messages = [lambda: f"{len(self.bot.guilds)}개의 서버에서 사용 중",
                                lambda: "간단한 다기능 애플리케이션",]
        self.Current_Message_Index = 0
        
        # 애플리케이션 종료 시 캐시 삭제 예약
        atexit.register(self.Cleanup_Cache)

    # 캐시 삭제 스크립트
    def Cleanup_Cache(self):
        for root, dirs, files in os.walk('.'):
            if '__pycache__' in dirs:
                try:
                    shutil.rmtree(os.path.join(root, '__pycache__'))
                except:
                    pass

    @commands.Cog.listener()
    async def on_ready(self):
        # 런처 실행 로그 출력
        print('[Launcher] 애플리케이션과 연결했습니다.')
        print('-----------------------------------')
        print(f'애플리케이션 이름: {APP_NAME}')
        print(f'애플리케이션 ID: {self.bot.user.id}')
        print(f'애플리케이션 버전: {APP_VER}')
        print('-----------------------------------')

        # 슬래쉬 커맨드 동기화 스크립트
        await self.bot.sync_commands(guild_ids=[DEBUG_GUILD])
        print('[Launcher] 슬래쉬 커맨드를 동기화했습니다.')

        # Presence 변경 작업이 실행 중이지 않으면 시작
        if not self.Change_Presence.is_running():
            self.Change_Presence.start()
            print("[Launcher] 상태 메세지 변경 작업을 시작했습니다.")

    @tasks.loop(seconds=5)
    async def Change_Presence(self):
        # 현재 인덱스의 메세지로 Presence 설정
        Status_Message = self.Status_Messages[self.Current_Message_Index]()
        Activity = discord.Activity(
            type=discord.ActivityType.playing,
            name=Status_Message
        )
        await self.bot.change_presence(activity=Activity)

        # 다음 메세지로 인덱스 순환 (리스트 길이를 초과하면 0으로 초기화)
        self.Current_Message_Index = (self.Current_Message_Index + 1) % len(self.Status_Messages)

    @Change_Presence.before_loop
    async def Before_Change_Presence(self):
        # 애플리케이션이 준비될 때까지 대기
        await self.bot.wait_until_ready()

def setup(bot):
    bot.add_cog(Launcher(bot))