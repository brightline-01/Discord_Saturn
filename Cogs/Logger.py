import discord, os, datetime, sys
from discord.ext import commands
from Config import APP_NAME

# 로그 출력을 여러 곳으로 보내는 클래스입니다.
class MultiLogger:
    def __init__(self, *streams):
        # 출력 대상 저장
        self.streams = streams

    # print()가 호출될 때 자동 실행
    def write(self, message: str):
        if not message.strip():
            return

        # 로그 포맷 생성
        Timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        Formatted = f"[{Timestamp}] {message}"

        # 모든 스트림에 기록
        for stream in self.streams:
            stream.write(Formatted)

    def flush(self):
        for stream in self.streams:
            stream.flush()

# 로그 기록을 담당하는 Cog입니다.
class Logger(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # 로그 디렉토리 생성
        os.makedirs("Logs", exist_ok=True)

        # 애플리케이션 실행 일시를 기반으로 로그 파일명 생성
        LOG_NAME = f"Logs/{APP_NAME}_Log_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"

        # 로그 파일 열기
        self.LOG_FILE = open(LOG_NAME, "a", encoding="utf-8")

        # 원본 stdout/stderr 저장
        self.ORIGINAL_STDOUT = sys.stdout
        self.ORIGINAL_STDERR = sys.stderr

        # stdout/stderr를 MultiLogger로 교체하여 콘솔과 파일에 동시 출력
        sys.stdout = MultiLogger(self.ORIGINAL_STDOUT, self.LOG_FILE)
        sys.stderr = MultiLogger(self.ORIGINAL_STDERR, self.LOG_FILE)

        print("[Logger] 로깅 시스템을 초기화했습니다.")

    # Cog 언로드 시 자동으로 실행됩니다.
    def cog_unload(self):
        print("[Logger] 로깅 시스템을 종료합니다.")

        # 원본 스트림 복원
        sys.stdout = self.ORIGINAL_STDOUT
        sys.stderr = self.ORIGINAL_STDERR

        # 로그 파일 닫기
        self.LOG_FILE.close()

async def setup(bot):
    await bot.add_cog(Logger(bot))