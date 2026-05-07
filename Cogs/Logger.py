import discord, os, datetime, sys
from discord.ext import commands
from Config import APP_NAME

# stdout/stderr를 가로채는 클래스
class MultiLogger:
    def __init__(self, *streams):
        self.streams = streams

    # print()가 실행될 때 같이 실행
    def write(self, message: str):
        # 빈 문자열이나 줄바꿈에는 타임스탬프를 붙이지 않음
        if message.strip() == "":
            for stream in self.streams:
                stream.write(message)
                stream.flush()
            return

        LOG_FORMAT = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"

        for stream in self.streams:
            stream.write(LOG_FORMAT)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()

# 로그 기록을 담당하는 Cog
class Logger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # 로그 디렉토리 생성
        os.makedirs("Logs", exist_ok=True)

        # 애플리케이션 실행 일시를 기반으로 로그 파일명 생성
        LOG_NAME = f"Logs/{APP_NAME}_Log_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"

        # 로그 파일 생성 및 불러오기
        self.LOG_FILE = open(LOG_NAME, "a", encoding="utf-8")

        # stdout/stderr를 가로채서 로그 파일에 동시 출력
        sys.stdout = MultiLogger(sys.stdout, self.LOG_FILE)
        sys.stderr = MultiLogger(sys.stderr, self.LOG_FILE)

        print("[Logger] 로깅 시스템을 초기화했습니다.")

def setup(bot):
    bot.add_cog(Logger(bot))