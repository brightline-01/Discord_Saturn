import discord
from discord.ext import commands
from Config import APP_NAME, APP_VER

class Launcher(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.Status_Messages = [lambda: f"{len(self.bot.guilds)}개의 서버에서 사용 중", 
                                lambda: "간단한 다기능 애플리케이션"]
        self.Current_Message_Index = 0

    # 런처 실행 로그 출력
    @commands.Cog.listener()
    async def on_ready(self):
        print(' ')
        print('-----------------------------------')
        print('[Launcher] 애플리케이션과 연결했습니다.')
        print(f'애플리케이션 이름: {APP_NAME}')
        print(f'애플리케이션 ID: {bot.user.id}')
        print(f'애플리케이션 버전: {APP_VER}')
        print('-----------------------------------')
        print(' ')

        if not self.Change_Presence.is_running():
            self.Change_Presence.start()
            print("[Launcher] Presence 변경 작업을 시작했습니다.")

    # Presence 변경 스크립트
    @tasks.loop(seconds=5)
    async def Change_Presence(self):
        Status_Message = self.Status_Messages[self.Current_Message_Index]()
        Activity = discord.Activity(type=discord.ActivityType.playing, name=Status_Message)

        await self.bot.change_presence(activity=Activity)

        self.Current_Message_Index = (self.Current_Message_Index + 1) % len(self.Status_Messages)

    @Change_Presence.before_loop
    async def Before_Change_Presence(self):
        await self.bot.wait_until_ready()
    
def setup(bot):
    bot.add_cog(Launcher(bot))