import datetime
import discord

# 현재 시각을 한국어 형식으로 반환
def Current_Time() -> str:
    return datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')

# 오류 다이얼로그 Embed
def Error_Dialog_Embed(message: str) -> discord.Embed:
    return discord.Embed(description=f"⚠️ {message}", color=discord.Color.red())