import discord
from discord.ext import commands, tasks

class presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_message = [
        discord.Activity(type=discord.ActivityType.playing, name=f"-개의 서버에서 사용"),
        discord.Activity(type=discord.ActivityType.playing, name="간단한 다기능 애플리케이션")
        ]
        self.cur_status_index = 0

    @commands.Cog.listener()
    async def on_ready(self):
        self.status_message[0] = discord.Activity(type=discord.ActivityType.playing, name=f"{len(self.bot.guilds)}개의 서버에서 사용")
        await self.bot.change_presence(activity=self.status_message[self.cur_status_index])

        if not self.change_presence.is_running():
            self.change_presence.start()
            print("[Presence] Presence 변경 작업을 시작했습니다.")
        else:
            print("[Presence] Presence 변경 작업이 이미 진행 중이므로 시작하지 않습니다.")
    
    @tasks.loop(seconds=5)
    async def change_presence(self):
        await self.bot.change_presence(activity=self.status_message[self.cur_status_index])
        self.cur_status_index = (self.cur_status_index + 1) % len(self.status_message)

def setup(bot):
    bot.add_cog(presence(bot))