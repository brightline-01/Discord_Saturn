import discord
import datetime
import requests
from googletrans import Translator
from tkinter import*
from discord.ext import commands

class utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def exchCur(src, amount, dst):
        request = requests.get(f"https://cdn.jsdelivr.net/gh/fawazahmed0/currency-api@1/latest/currencies/{src}/{dst}.min.json")

        result = request.json()
        total = result[f'{dst}'] * amount

        return total
        
    Utility = discord.SlashCommandGroup("유틸리티")

    @Utility.command(name="번역", description="메세지를 번역하여 전송합니다.", options=[
        discord.Option(str, name="언어", description="번역할 언어 (ex: ko, en)", required=True),
        discord.Option(str, name="메세지", description="번역할 메세지", required=True)])
    async def transsend(self, ctx, target_language: str, *, message_to_translate: str):
        try:
            translated = await Translator().translate(message_to_translate, dest=target_language)
            await ctx.respond(f"**{ctx.author.display_name}:** {translated.text}")
        except Exception as e:
            await ctx.respond(embed=discord.Embed(description=":warning: 번역 중 예상치 못한 오류가 발생했습니다. ({e})"), ephemeral=True)
            print(f"[Command | Utility] 메세지 번역 중 예상치 못한 오류가 발생했습니다. (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, {e})")

    @Utility.command(name="환율", description="환율을 표시합니다.", options=[
        discord.Option(str, name="단위1", description="원래 단위 (ex: KRW, USD)", required=True),
        discord.Option(float, name="양", description="돈의 양", required=True),
        discord.Option(str, name="단위2", description="변환할 단위 (ex: USD, JPY)", required=True)])
    async def exchange(interaction: discord.Interaction, src: str, amount: float, dst: str):
        result = ex.exchCur(src, amount, dst)
        src = src.upper()
        dst = dst.upper()
        
        embed = discord.Embed(title=f"{src} -> {dst}", color=discord.Color.blue())
        embed.add_field(name=src, value=f"{amount} {src}", inline=True)
        embed.add_field(name=dst, value=f"{result} {dst}", inline=True)
        embed.set_footer(text="환율 정보는 실시간 API 기준입니다.")

def setup(bot):
    bot.add_cog(utility(bot))