import discord
import datetime
import sys
import os
from discord.ext import commands
from bot_token import token

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="::", intents=intents)
cogs_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'Cogs')

for ext in os.listdir(cogs_path):
    if ext.endswith(".py"):
        bot.load_extension(f"Cogs.{ext.split('.')[0]}")

@bot.event
async def on_ready():
    print(' ')
    print('-----------------------------------')
    print('[Launcher] 애플리케이션과 연결했습니다.')
    print(f'애플리케이션 이름: {bot.user}')
    print(f'애플리케이션 ID: {bot.user.id}')
    print(f'애플리케이션 버전: v1.2')
    print('-----------------------------------')
    print(' ')
    await bot.sync_commands()
    
os.makedirs("logs", exist_ok=True)
log_file = open(f"logs/botlog_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt", "a", encoding="utf-8")

class Logger:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, msg):
        for s in self.streams:
            s.write(msg)
            s.flush()
    def flush(self):
        for s in self.streams:
            s.flush()

sys.stdout = Logger(sys.stdout, log_file)
sys.stderr = Logger(sys.stderr, log_file)

bot.run(token)