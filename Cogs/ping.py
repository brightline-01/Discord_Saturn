import discord
import datetime
from discord.ext import commands

class ping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(name="핑", description="애플리케이션의 레이턴시를 표시합니다.")
    async def ping(self, ctx):
        ping = round(self.bot.latency * 1000)
        embed = discord.Embed(title="퐁! :ping_pong: ", color=discord.Color.blue())
        embed.add_field(name="애플리케이션 레이턴시", value=f"{ping} ms", inline=True)
        embed.add_field(name="애플리케이션 서버 위치", value="대한민국, 서울", inline=True)
        embed.set_footer(text=f"일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.respond(embed=embed)
        print(f"[Command | General] 사용자가 애플리케이션의 레이턴시를 요청했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

def setup(bot):
    bot.add_cog(ping(bot))