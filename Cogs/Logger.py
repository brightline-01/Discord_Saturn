import discord, os, datetime, sys
from discord.ext import commands
from Config import APP_NAME

# 로그 동시 출력 스크립트
class MultiLogger:
    def __init__(self, *Streams):
        self.Streams = Streams

    def write(self, Message: str):
        LOG_FORMAT = (Message if not Message.strip() else f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {Message}")

        for Stream in self.Streams:
            Stream.write(LOG_FORMAT)
            Stream.flush()

    def flush(self):
        for Stream in self.Streams:
            Stream.flush()

class Logger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # 로그 디렉토리 생성
        os.makedirs("Logs", exist_ok=True)

        # 로그 파일 이름 생성
        LOG_PATH = f"Logs/{APP_NAME}_Log_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"

        # 로그 파일 생성 및 불러오기
        self.LOG_FILE = open(LOG_PATH, "a", encoding="utf-8")

        # 로그를 콘솔과 로그 파일에 동시 출력
        sys.stdout = sys.stderr = MultiLogger(sys.stdout, self.LOG_FILE)

        print("[Logger] 로깅 시스템을 초기화했습니다.")

def setup(bot):
    bot.add_cog(Logger(bot))