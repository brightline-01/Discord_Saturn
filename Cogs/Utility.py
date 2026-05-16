import discord, aiohttp
from discord.ext import commands
from googletrans import Translator
from Resources import Error_Dialog_Embed, Current_Time

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    Utility_CMDGroup = discord.SlashCommandGroup("유틸리티")

    # /유틸리티 핑
    @Utility_CMDGroup.command(name="핑", description="애플리케이션의 레이턴시를 표시합니다.")
    async def Ping(self, ctx):
        Latency = round(self.bot.latency * 1000)
        await ctx.respond(embed=discord.Embed(title="🏓 퐁!", color=discord.Color.blue())
        .add_field(name="애플리케이션 레이턴시", value=f"{Latency} ms", inline=True)
        .add_field(name="애플리케이션 서버 위치", value="대한민국, 서울", inline=True)
        .set_footer(text=f"일시: {Current_Time()}"))

    # /유틸리티 번역 [내용] [언어]
    @Utility_CMDGroup.command(name="번역", description="텍스트를 다른 언어로 번역하여 전송합니다.")
    async def Translate(self, ctx, Text: discord.Option(str, name="내용", description="번역할 내용"),
        Dest: discord.Option(str, name="언어", description="번역할 언어 코드 (ex: ko, en, ja)")):
        
        try:
            await ctx.defer()
            Result = Translator().translate(Text, dest=Dest)
            await ctx.respond(f"**{ctx.author.mention}**: {Result.text}")
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"메세지를 번역하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

    # /유틸리티 환율 [기준] [변환] [금액]
    @Utility_CMDGroup.command(name="환율", description="실시간 환율 정보를 표시합니다.")
    async def Exchange_Rate(self, ctx, Base: discord.Option(str, name="기준", description="기준 통화를 입력하세요. (ex: KRW, USD)"),
        Target: discord.Option(str, name="변환", description="변환할 통화를 입력하세요. (ex: USD, JPY)"),
        Amount: discord.Option(float, name="금액", description="변환할 금액을 입력하세요. (선택)", required=False, default=1.0)):
        
        await ctx.defer()

        try:
            async with aiohttp.ClientSession() as Session:
                async with Session.get(f"https://api.exchangerate-api.com/v4/latest/{Base.upper()}") as Response:
                    if Response.status != 200:
                        return await ctx.respond(embed=Error_Dialog_Embed(f"환율 정보 API 서버가 원활하지 않습니다. (상태 코드: {Response.status})"), ephemeral=True)
                    
                    Data = await Response.json()
                    Rate = Data.get("rates", {}).get(Target.upper())
                        
                if not Rate:
                    return await ctx.respond(embed=Error_Dialog_Embed(f"'{Target.upper()}'에 해당하는 통화를 찾을 수 없습니다."), ephemeral=True)

                Converted_Amount = Amount * Rate
                
                Embed = discord.Embed(title=f"💹 환율 정보를 표시합니다. ({Base.upper()} -> {Target.upper()})", color=discord.Color.blue())
                Embed.add_field(name="기준 금액", value=f"{Amount:,.2f} {Base.upper()}", inline=True)
                Embed.add_field(name="변환된 금액", value=f"{Converted_Amount:,.2f} {Target.upper()}", inline=True)
                Embed.add_field(name="기준 환율", value=f"1 {Base.upper()} = {Rate:,.2f} {Target.upper()}", inline=False)
                Embed.set_footer(text=f"업데이트 일시: {Data.get('date')} | {Current_Time()}")
                await ctx.respond(embed=Embed)
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"환율 정보를 표시하는 중 오류가 발생했습니다. ({e})"), ephemeral=True)

def setup(bot):
    bot.add_cog(Utility(bot))