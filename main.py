import discord
import datetime
import sys
import os
from discord.ext import commands
from bot_token_pre import token

# Todo:
# - 주식 불러오기
# - 환율 불러오기
# - 학교정보 불러오기
# - 날씨정보 불러오기
# - 물건 가격 불러오기

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="::", intents=intents)
cogs_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'Cogs')

# Cogs 로드 스크립트
for ext in os.listdir(cogs_path):
    if ext.endswith(".py"):
        bot.load_extension(f"Cogs.{ext.split('.')[0]}")

# on_ready 스크립트
@bot.event
async def on_ready():
    # 런처 로그 출력
    print(' ')
    print('-----------------------------------')
    print('[Launcher] 애플리케이션과 연결했습니다.')
    print(f'애플리케이션 이름: {bot.user}')
    print(f'애플리케이션 ID: {bot.user.id}')
    print(f'애플리케이션 버전: v1.0')
    print('-----------------------------------')
    print(' ')
    # 슬래쉬 커맨드 sync 스크립트
    await bot.sync_commands(guild_ids=[1456526224296902739])
    

# txt 로깅 스크립트
os.makedirs("Logs", exist_ok=True)
log_file = open(f"Logs/Saturn_Log_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt", "a", encoding="utf-8")

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