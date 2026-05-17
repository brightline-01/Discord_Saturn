import discord, sys, os, subprocess
from discord.ext import commands
from Resources import Print_Log, Error_Dialog_Embed, Success_Dialog_Embed

class System(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        # 애플리케이션의 메세지이거나 다이렉트 메세지가 아닌 경우 무시
        if message.author.bot or not isinstance(message.channel, discord.DMChannel):
            return

        # 재시작 명령어
        if message.content == "!재시작":
            # 애플리케이션 소유자 검증
            if await self.bot.is_owner(message.author):
                await message.reply(embed=Success_Dialog_Embed("애플리케이션 서버를 재시작합니다."))
                Print_Log("System", "애플리케이션 서버 재시작을 요청했습니다.", "다이렉트 메세지", message.author.name)
                
                # 애플리케이션 서버 재시작 (Windows)
                os.system("shutdown /r /t 0")
            else:
                await message.reply(embed=Error_Dialog_Embed("애플리케이션 소유자만 실행할 수 있습니다."))

        # 업데이트 명령어
        if message.content == "!업데이트":
            # 애플리케이션 소유자 검증
            if await self.bot.is_owner(message.author):
                await message.reply(embed=Success_Dialog_Embed("애플리케이션 업데이트를 시작합니다."))
                Print_Log("System", "애플리케이션 업데이트를 요청했습니다.", "다이렉트 메세지", message.author.name)
                
                # git pull 실행
                try:
                    Process = subprocess.run(["git", "pull"], capture_output=True, text=True)
                    if Process.returncode == 0:
                        await message.reply(embed=Success_Dialog_Embed(f"업데이트가 완료되었습니다. 애플리케이션을 재시작합니다."))
                        # 애플리케이션 재시작
                        os.execv(sys.executable, ['python'] + sys.argv)
                    else:
                        await message.reply(embed=Error_Dialog_Embed(f"업데이트 중 오류가 발생했습니다."))
                except Exception as e:
                    await message.reply(embed=Error_Dialog_Embed(f"업데이트 중 오류가 발생했습니다 ({e})"))
            else:
                await message.reply(embed=Error_Dialog_Embed("애플리케이션 소유자만 실행할 수 있습니다."))

        # 로그 명령어
        if message.content == "!로그":
            # 애플리케이션 소유자 검증
            if await self.bot.is_owner(message.author):
                try:
                    if not os.path.exists("Logs"):
                        return await message.reply(embed=Error_Dialog_Embed("Logs 폴더가 존재하지 않습니다."))

                    Log_Files = [os.path.join("Logs", f) for f in os.listdir("Logs") if os.path.isfile(os.path.join("Log", f))]
                    if not Log_Files:
                        return await message.reply(embed=Error_Dialog_Embed("로그 파일이 존재하지 않습니다."))

                    # 가장 최근에 수정된 파일 찾기
                    Latest_Log = max(Log_Files, key=os.path.getmtime)

                    # Discord 파일로 전송
                    await message.reply(embed=Success_Dialog_Embed(f"로그 파일을 전송합니다."), file=discord.File(Latest_Log))
                    Print_Log("System", "로그 파일을 전송했습니다.", "다이렉트 메세지", message.author.name)
                except Exception as e:
                    await message.reply(embed=Error_Dialog_Embed(f"로그 파일을 전송하는 중 오류가 발생했습니다 ({e})"))
            else:
                await message.reply(embed=Error_Dialog_Embed("애플리케이션 소유자만 실행할 수 있습니다."))

    # 애플리케이션 오류 전송 스크립트
    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        # 기본적인 오류 무시
        if isinstance(error, commands.CommandNotFound):
            return

        # 오류 상세 정보 생성
        Error_Message = f"⚠️ **애플리케이션에서 오류가 발생했습니다.**\n\n"
        Error_Message += f"**명령어**: {ctx.command.qualified_name if ctx.command else '알 수 없음'}\n"
        Error_Message += f"**서버**: {ctx.guild.name if ctx.guild else '다이렉트 메세지'}\n"
        Error_Message += f"**사용자**: {ctx.author.name} ({ctx.author.id})\n"
        Error_Message += f"**오류**: ```py\n{error}\n```"

        # 소유자에게 전송
        try:
            Owner = (await self.bot.application_info()).owner
            await Owner.send(Error_Message)
        except Exception as e:
            Print_Log("System", f"소유자에게 오류 메세지를 전송하는 중 오류가 발생했습니다. ({e})", "시스템", "시스템")

        # 로그 출력
        Print_Log("System", "애플리케이션에서 오류를 감지했습니다.", ctx.guild.name if ctx.guild else "다이렉트 메세지", ctx.author.name, Extra=str(error))

    # 시스템 전역 오류 핸들러
    @commands.Cog.listener()
    async def on_error(self, event, *args, **kwargs):
        import traceback
        Error_Content = traceback.format_exc()
        
        Error_Message = f"⚠️ **애플리케이션에서 치명적인 오류가 발생했습니다.**\n\n"
        Error_Message += f"**이벤트**: {event}\n"
        Error_Message += f"**오류**: ```py\n{Error_Content[:1800]}\n```"

        try:
            Owner = (await self.bot.application_info()).owner
            await Owner.send(Error_Message)
        except:
            pass
            
        Print_Log("System", "애플리케이션에서 치명적인 오류를 감지했습니다.", "시스템", "시스템", Extra=event)

def setup(bot):
    bot.add_cog(System(bot))