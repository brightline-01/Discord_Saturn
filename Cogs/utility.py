import discord
import datetime
from googletrans import Translator
from tkinter import*
from discord.ext import commands

class utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
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

def setup(bot):
    bot.add_cog(utility(bot))