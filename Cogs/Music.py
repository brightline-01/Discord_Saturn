import discord
import datetime
import re
import asyncio
import random
from discord.ext import commands
from pytubefix import YouTube, Search, Playlist
from Resources import Current_Time, Error_Dialog_Embed, Success_Dialog_Embed, Print_Log

# YouTube URL 검증 스크립트
def Check_YouTube_URL(Text):
    return bool(re.match(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/", Text))

# YouTube 재생 목록 URL 검증 스크립트
def Check_Playlist_URL(URL):
    return "list=" in URL

# MusicPlayer 클래스
class MusicPlayer:
    def __init__(self, bot, FFmpeg_Options: dict):
        self.bot = bot
        self.FFmpeg_Options = FFmpeg_Options
        self.Voice: discord.VoiceClient | None = None
        self.Queue = []
        self.History = []
        self.Current = None
        self.Lock = asyncio.Lock()
        self.Loop = False
        self.Loop_Queue = False
        self.On_Song_Start = None
        self.Suppress_Next_Start_Embed = False
        self.Volume = 1.0
        self.Manual_Stop = False
    
    # 음악 재생 상태 확인 스크립트
    def Is_Playing(self):
        return self.Voice and self.Voice.is_playing()

    # 음악 일시 정지 상태 확인 스크립트
    def Is_Paused(self):
        return self.Voice and self.Voice.is_paused()

    # 음악 재생 스크립트
    async def Play(self, URL: str, Info: dict):
        async with self.Lock:
            try:
                # 오디오 소스 생성 및 현재 음악 정보 저장
                Source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(URL, **self.FFmpeg_Options), volume=self.Volume)
                self.Current = {"URL": URL, "Info": Info}

                if self.On_Song_Start and not any([self.Suppress_Next_Start_Embed, self.Loop, self.Loop_Queue]):
                    await self.On_Song_Start(Info)

                self.Suppress_Next_Start_Embed = False
                self.Voice.play(Source, after=lambda Error: self.bot.loop.create_task(self.After_Play(Error)))
            except Exception as Error:
                Guild = Info["Text_Channel"].guild.name if Info else "알 수 없음"
                Print_Log("Music", "음악을 재생하는 중 오류가 발생했습니다.", Guild, "애플리케이션 (MusicPlayer)", Extra=f"({Error})")

    # 음악 재생 완료 후 스크립트
    async def After_Play(self, Error):
        # 재생 중 오류 발생 여부 확인
        if Error:
            Info = self.Current["Info"] if self.Current else None
            Guild = Info["Text_Channel"].guild.name if Info else "알 수 없음"
            Print_Log("Music", "음악을 재생하는 중 오류가 발생했습니다.", Guild, "애플리케이션 (MusicPlayer)", Extra=f"({Error})")

        # 수동 정지 여부 확인
        if self.Manual_Stop:
            self.Manual_Stop = False
            return
 
        # 음악 반복 재생 여부 확인
        if self.Loop and self.Current:
            return await self.Play(**self.current)
        
        # 재생 기록 저장
        if self.Current:
            self.History.append(self.Current)
            
        # 대기열 반복 재생 여부 확인
        if self.Loop_Queue:
            self.Queue.append(self.Current)
        
        # 다음 음악 재생
        await self.Play_Next()

    # 다음 음악 재생 스크립트
    async def Play_Next(self):
        # 대기열에 음악이 없는 경우 확인
        if not self.Queue:
            self.Current = None
 
            # 음성 연결을 해제함
            if self.Voice and self.Voice.is_connected():
                await self.Voice.disconnect()
            
            self.Voice = None
            return
 
        # 음악 재생
        await self.Play(**self.Queue.pop(0))

    # 대기열에 음악 추가 스크립트
    def Add_To_Queue(self, URL: str, Info: dict):
        self.Queue.append({"URL": URL, "Info": Info})

    # 이전 음악 재생 스크립트
    async def Play_Previous(self):
        # 재생 기록 확인
        if not self.History:
            return False
 
        # 이전 음악 가져오기
        Prev = self.History.pop()
        self.Manual_Stop = True
        Loop, Queue_Loop = self.Loop, self.Loop_Queue
        self.Loop = self.Loop_Queue = False
 
        # 현재 음악을 대기열에 추가
        if self.Current:
            self.Queue.insert(0, self.Current)
        
        # 음악 정지
        if self.Is_Playing():
            self.Voice.stop()
        
        # 이전 음악 재생
        await self.Play(**Prev)
        self.Loop, self.Loop_Queue = Loop, Queue_Loop
        return True

    # 음악 일시 정지 스크립트
    def Pause(self):
        if self.Is_Playing():
            self.Voice.pause()
 
    # 음악 재개 스크립트
    def Resume(self):
        if self.Is_Paused():
            self.Voice.resume()
 
    # 음악 건너뛰기 스크립트
    def Skip(self):
        if self.Is_Playing():
            self.Voice.stop()
 
    # 음악 정지 스크립트
    async def Stop(self):
        # 대기열 및 재생 기록 제거
        self.Queue.clear()
        self.History.clear()
        self.Current = None
 
        # 음성 연결 해제
        if self.Voice:
            self.Voice.stop()

            if self.Voice.is_connected():
                await self.Voice.disconnect()

        self.Voice = None
 
    # 볼륨 조절 스크립트 (최소 0% ~ 최대 500%)
    def Set_Volume(self, Volume: float):
        self.Volume = max(0.0, min(Volume, 5.0))
 
        if self.Voice and self.Voice.source:
            self.Voice.source.volume = self.Volume
 
    # 대기열에서 음악 재생 스크립트
    async def Play_From_Queue(self, Position: int):
        # 대기열 범위 확인
        if not 1 <= Position <= len(self.Queue):
            return False
 
        # 현재 재생 중인 음악을 재생 기록에 추가
        if self.Current:
            self.History.append(self.Current)
        
            # 대기열 반복 재생 설정 시 현재 음악 추가
            if self.Loop_Queue:
                self.Queue.append(self.Current)
 
        # 대기열에서 음악 제거
        Song = self.Queue.pop(Position - 1)
        self.Manual_Stop = True
 
        # 음악 정지
        if self.Is_Playing():
            self.Voice.stop()
 
        # 음악 재생
        await self.Play(**Song)
        return True
    
    # 대기열 셔플 스크립트
    async def Shuffle_Queue(self):
        if not self.Queue or len(self.Queue) < 2:
            return False
 
        random.shuffle(self.Queue)
        return True

# QueueView 클래스
class QueueView(discord.ui.View):
    def __init__(self, ctx, Player, Queue_Page_Function):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.Player = Player
        self.Queue_Page = Queue_Page_Function
        self.Page = 1
        self.Update_Buttons()
 
    # 버튼 생성
    def Create_Button(self, Emoji, Enabled, Callback):
        Button = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji=Emoji, disabled=not Enabled)
        Button.callback = Callback
        return Button

    # 버튼 업데이트 스크립트
    def Update_Buttons(self):
        self.clear_items()
        Total_Pages = max(1, (len(self.Player.Queue) + 9) // 10)

        Buttons = [
            ("⏪", self.Page > 1, lambda i: self.Update_Page(i, 1)),
            ("⬅️", self.Page > 1, lambda i: self.Update_Page(i, -1)),
            ("➡️", self.Page < Total_Pages, lambda i: self.Update_Page(i, 1)),
            ("⏩", self.Page < Total_Pages, lambda i: self.Update_Page(i, Total_Pages))
        ]
 
        for Emoji, Enabled, Callback in Buttons:
            self.add_item(self.Create_Button(Emoji, Enabled, Callback))
 
    # 대기열 메세지 업데이트 스크립트
    async def Update_Page(self, Interaction, Page):
        self.Page = Page
        embed, _ = self.Queue_Page(self.ctx, self.Player, self.Page)

        self.Update_Buttons()
        await Interaction.response.edit_message(embed=embed, view=self)

# VoteView 클래스
class VoteView(discord.ui.View):
    def __init__(self, ctx, Player, Required_Votes, Action, Success_Message: str):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.Player = Player
        self.Required_Votes = Required_Votes
        self.Votes = set()
        self.Action = Action
        self.Success_Message = Success_Message
 
    # 투표 스크립트
    @discord.ui.button(label="투표하기", style=discord.ButtonStyle.danger)
    async def Vote(self, Button: discord.ui.Button, Interaction: discord.Interaction):
        # 사용자 검증
        if Interaction.user.bot:
            return

        if Interaction.user not in self.ctx.author.voice.channel.members:
            return await Interaction.response.send_message(embed=Error_Dialog_Embed("음성 채널에 있는 사용자만 투표할 수 있습니다."), ephemeral=True)
 
        if Interaction.user.id in self.Votes:
            return await Interaction.response.send_message(embed=Error_Dialog_Embed("이미 투표하셨습니다."), ephemeral=True)
 
        self.Votes.add(Interaction.user.id)
 
        # 투표 결과 처리
        if len(self.Votes) >= self.Required_Votes:
            await self.Action()
            self.stop()
            return await Interaction.response.edit_message(embed=Success_Dialog_Embed(self.Success_Message.replace(":white_check_mark: ", "")), view=None)
 
        await Interaction.response.edit_message(embed=discord.Embed(description=f"투표가 진행 중입니다.\n"f"찬성: **{len(self.Votes)} / {self.Required_Votes}**"), view=self)

# PlaylistConfirmView 클래스
class PlaylistConfirmView(discord.ui.View):
    def __init__(self, Author, Playlist_URL, Player):
        super().__init__(timeout=30)
        self.Author = Author
        self.Playlist_URL = Playlist_URL
        self.Player = Player
        self.Value = None
 
    # 인터랙션 사용자 검증 스크립트
    async def Interaction_Check(self, Interaction: discord.Interaction) -> bool:
        if Interaction.user == self.Author:
            return True

        await Interaction.response.send_message(embed=Error_Dialog_Embed("이 버튼은 명령어를 실행한 사용자만 사용할 수 있습니다."), ephemeral=True)
        return False
 
    # 버튼 처리
    async def Set_Value(self, Interaction, Value):
        self.Value = Value
        await Interaction.response.defer()
        self.stop()

    # 재생 목록 음악 추가 반환
    @discord.ui.button(label="추가하기", style=discord.ButtonStyle.green)
    async def Confirm(self, Button: discord.ui.Button, Interaction: discord.Interaction):
        await self.Set_Value(Interaction, True)
 
    # 재생목록 음악 추가 취소 반환
    @discord.ui.button(label="취소", style=discord.ButtonStyle.red)
    async def Cancel(self, Button: discord.ui.Button, Interaction: discord.Interaction):
        await self.Set_Value(Interaction, False)
 
    # 시간 초과 스크립트
    async def On_Timeout(self):
        for Item in self.children:
            Item.disabled = True

# Music 클래스
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.FFmpeg_Options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
            }
        self.Pytubefix_Options = {'only_audio': True, 'abr': '160kbps'}
        self.Players = {}
 
    # 애플리케이션 자동 퇴장 스크립트
    @discord.Cog.listener()
    async def on_voice_state_update(self, Member, Before, After):
        # 애플리케이션 제외
        if Member.bot:
            return
 
        # 서버 별 플레이어 지정
        Player = self.Players.get(Member.guild.id)
 
        # 플레이어 및 음성 채널 확인
        if not Player or not Player.Voice or not Player.Voice.channel:
            return
 
        # 멤버가 없다면 자동으로 퇴장
        if not any(not M.bot for M in Player.Voice.channel.members):
            await Player.Stop()

    # 음악 정보 생성 스크립트
    def Build_Song_Info(self, YT, ctx, Queue_Position=0):
        return {
            "Title": YT.title,
            "Url": YT.watch_url,
            "Webpage_URL": YT.watch_url,
            "Duration": YT.length,
            "Uploader": YT.author,
            "Thumbnail": YT.thumbnail_url,
            "Requester": ctx.author.display_name,
            "Text_Channel": ctx.channel
        }

    # 음악 길이 포맷 스크립트
    def Format_Duration(self, Seconds: int) -> str:
        if Seconds is None:
            return "알 수 없음"

        M, S = divmod(Seconds, 60)
        H, M = divmod(M, 60)

        return f"{H}:{M:02d}:{S:02d}" if H else f"{M}:{S:02d}"
    
    # 음악 Embed 생성 스크립트
    async def Build_Embed(self, Song_Info, ctx, Description):
        embed = discord.Embed(
            title=(f"🎵 {Song_Info['Title']}"),
            description=Description,
            url=Song_Info.get('Webpage_URL'),
            color=discord.Color.blue()
        )
        embed.add_field(name="영상 길이", value=self.Format_Duration(Song_Info['Duration']), inline=True)
        embed.add_field(name="채널", value=Song_Info['Uploader'], inline=True)
        embed.set_thumbnail(url=Song_Info['Thumbnail'])
        embed.set_footer(text=f"요청자 : {Song_Info['Requester']} | 일시: {Current_Time()}")
        return embed
    
    # 음악 재생 시작 Embed 전송 스크립트
    async def Send_Embed(self, Song_Info):
        if Channel := Song_Info.get("Text_Channel"):
            await Channel.send(embed=await self.Build_Embed(Song_Info, None, f"**{Song_Info['Title']}** 음악을 재생하고 있습니다."))

    # 대기열 페이지 생성 스크립트
    def Queue_Page(self, ctx, Player: MusicPlayer, Page_Num: int, Songs_Per_Page=10):
        Queue = Player.Queue
        Start_Index = (Page_Num - 1) * Songs_Per_Page
        End_Index = Start_Index + Songs_Per_Page
 
        # 페이지 범위 검증
        if Start_Index >= len(Queue):
            return None, None
 
        # 대기열 Embed 생성
        embed = discord.Embed(title="🎶 대기열을 표시합니다.", description="현재 대기열 목록:", color=discord.Color.blue())
 
        # 현재 재생 중인 음악 검증
        if Player.Current:
            Info = Player.Current["Info"]
            embed.add_field(name=f"현재 재생 중: {Info['Title']}", value=f"길이: {self.Format_Duration(Info['Duration'])} | 요청자: {Info['Requester']}",inline=False)
 
        # 음악 정보 추가
        for I, Song in enumerate(Queue[Start_Index:End_Index], Start=Start_Index + 1):
            Info = Song["Info"]
            embed.add_field(name=f"{I}. {Info['Title']}", value=f"길이: {self.Format_Duration(Info['Duration'])} | 요청자: {Info['Requester']}", inline=False)
 
        # 전체 페이지 수 계산
        Total_Pages = (len(Queue) + Songs_Per_Page - 1) // Songs_Per_Page
        embed.set_footer(text=f"페이지 {Page_Num} / {Total_Pages}")
 
        return embed, Total_Pages

    # 재생 목록 음악 추가 스크립트
    async def Add_Playlist_To_Queue(self, URL, ctx, Player):
        Added = 0
 
        # 재생 목록 객체 생성
        for YT in list(Playlist(URL).videos)[1:]:
            # 스트림 필터링
            Stream = YT.streams.filter(**self.Pytubefix_Options).order_by("abr").desc().first()
 
            if not Stream:
                continue
 
            # 대기열에 음악 추가
            Player.Add_To_Queue(Stream.url, self.Build_Song_Info(YT, ctx))
            Added += 1
        
        await ctx.respond(embed=Success_Dialog_Embed(f"재생 목록에서 음악 **{Added}개**를 대기열에 추가했습니다."))

    # 음성 채널 입장 스크립트
    async def Ensure_Voice_Channel(self, ctx, Player):
        # 음성 채널 연결 검증
        if not ctx.author.voice:
            await ctx.respond(embed=Error_Dialog_Embed("먼저 음성 채널에 연결해주세요."), ephemeral=True)
            return False
 
        Channel = ctx.author.voice.channel
 
        # 음성 채널 연결 상태 확인
        if ctx.voice_client:
            if ctx.voice_client.channel != Channel:
                await ctx.respond(embed=Error_Dialog_Embed("애플리케이션이 같은 서버의 다른 음성 채널에서 재생 중입니다. 애플리케이션의 연결을 끊거나 기다린 후 다시 시도하세요."), ephemeral=True)
                return False
            Player.Voice = ctx.voice_client
        else:
            Player.Voice = await Channel.connect()
 
        return True

    async def Control_Player_Action(self, ctx, Check, Action, Success_Message):
        # 서버 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)     
 
        # 음악 재생 상태 확인
        if not Player or not Check(Player):
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)
 
        # 음악 제어
        Action(Player)
        return await ctx.respond(embed=Success_Dialog_Embed(Success_Message))

    async def Check_Queue(self, ctx):
        # 서버 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)
 
        # 대기열 상태 확인
        if not Player or not Player.Queue:
            return await ctx.respond(embed=Error_Dialog_Embed("대기열에 음악이 없습니다."), ephemeral=True)
 
        return True

    Music = discord.SlashCommandGroup("음악")

    # /음악 재생 [제목]
    @Music.command(name="재생", description="YouTube에서 음악을 찾아 재생합니다.")
    async def Play_Music(self, ctx, URL: discord.Option(str, name="제목", description="재생할 음악의 제목 또는 URL", required=True)):
        await ctx.defer()
 
        # 서버 별 플레이어 지정
        Player = self.Players.setdefault(ctx.guild.id, MusicPlayer(self.bot, self.FFmpeg_Options))
        Player.On_Song_Start = self.Send_Embed
 
        # 음성 채널 입장
        if not await self.Ensure_Voice_Channel(ctx, Player):
            return

        # 음악 재생 또는 대기열에 추가
        async def Play_Or_Queue(Stream, Info):
            if Player.Is_Playing():
                Player.Add_To_Queue(Stream.url, Info)
                Desc = f"**{Info['Title']}** 음악을 대기열에 추가했습니다."
                Log = "대기열에 음악을 추가했습니다."
            else:
                Player.Suppress_Next_Start_Embed = True
                await Player.Play(Stream.url, Info)
                Desc = f"**{Info['Title']}** 음악을 재생하고 있습니다."
                Log = "음악을 재생했습니다."
            
            Print_Log("Music", Log, ctx.guild.name, ctx.author.name)
            await ctx.respond(embed=await self.Build_Embed(Info, ctx, Description=Desc))
 
        try:
            # 재생 목록 URL 검증
            if Check_Playlist_URL(URL):
                Videos = list(Playlist(URL).videos)

                # 재생 목록이 존재하는지 확인
                if not Videos:
                    return await ctx.respond(embed=Error_Dialog_Embed("재생 목록을 찾을 수 없습니다."))
                
                # 재생 목록 확인 View
                View = PlaylistConfirmView(ctx.author, URL, Player)
    
                # 첫 번째 음악 정보 추출
                First_Video = Videos[0]
                Stream = First_Video.streams.filter(**self.Pytubefix_Options).order_by("abr").desc().first()

                # 첫 번째 음악이 존재하는지 확인
                if not Stream:
                    return await ctx.followup.send(embed=Error_Dialog_Embed("재생 목록의 첫 번째 음악을 찾을 수 없습니다."))

                # 첫 번째 음악 재생
                await Play_Or_Queue(Stream, self.Build_Song_Info(First_Video, ctx))
                Message = await ctx.followup.send(embed=discord.Embed(title="📃 재생목록 링크를 감지했습니다.", description="이 재생목록의 모든 음악을 대기열에 추가할까요?"))
                await View.wait()

                for Item in View.children:
                    Item.disabled = True

                await Message.edit(view=View)

                # 시간 초과 처리
                if View.Value is None:
                    return await ctx.followup.send(embed=Error_Dialog_Embed("시간이 초과되어 동작을 실행하지 않습니다."))
                
                # 재생 목록 추가
                if View.Value:
                    await self.Add_Playlist_To_Queue(URL, ctx, Player)

                return await ctx.followup.send(embed=Success_Dialog_Embed("재생목록의 음악을 추가하지 않았습니다."))
 
            # YouTube URL 검증
            YT = YouTube(URL) if Check_YouTube_URL(URL) else (Search(URL).results[0] if Search(URL).results else None)
            
            if not YT:
                return await ctx.respond(embed=Error_Dialog_Embed("검색 결과를 찾을 수 없습니다."), ephemeral=True)
    
            # 음악 정보 저장
            Stream = YT.streams.filter(**self.Pytubefix_Options).order_by("abr").desc().first()
    
            if not Stream:
                return await ctx.respond(embed=Error_Dialog_Embed("음악을 찾을 수 없습니다."), ephemeral=True)

            # 음악 재생
            await Play_Or_Queue(Stream, self.Build_Song_Info(YT, ctx))
        except Exception as e:
            await ctx.respond(embed=Error_Dialog_Embed(f"음악을 재생하는 중 오류가 발생했습니다. {(e)}"), ephemeral=True)
            Print_Log("Music", "음악을 재생하는 중 오류가 발생했습니다.", ctx.guild.name, ctx.author.name, Extra=f"({e})")

    # /음악 검색 [제목] [개수]
    @Music.command(name="검색", description="YouTube에서 음악을 지정한 개수만큼 검색합니다.")
    async def Search_Music(self, ctx, Query: discord.Option(str, name="제목", description="검색할 음악의 제목", required=True),
        Index: discord.Option(int, name="개수", description="검색할 개수 (1 ~ 10, 선택)", required=False, min_value=1, max_value=10, default=3)):
        await ctx.defer()
        
        # 서버 별 플레이어 지정
        Player = self.Players.setdefault(ctx.guild.id, MusicPlayer(self.bot, self.FFmpeg_Options))
        Player.On_Song_Start = self.Send_Embed
 
        # 음성 채널 입장
        if not await self.Ensure_Voice_Channel(ctx, Player):
            return
        
        # 검색
        Search_Obj = Search(Query)
        Results = Search_Obj.results[:Index]
 
        # 검색 결과 확인
        if not Results:
            return await ctx.respond(embed=Error_Dialog_Embed("검색 결과가 없습니다."), ephemeral=True)
 
        # 검색 결과 표시
        Embed = discord.Embed(title=f":notes: '{Query}'에 대한 검색 결과", color=discord.Color.blue())
 
        for I, YT in enumerate(Results, start=1):
            Embed.add_field(name=f"{I}. {YT.title}", value=f"채널: {YT.author}\n길이: {self.Format_Duration(YT.length) if YT.length else "알 수 없음"}", inline=False)
 
        await ctx.respond(content=":white_check_mark: 30초 내에 번호를 입력하여 해당 음악을 재생할 수 있습니다.", embed=Embed)
        Print_Log("Music", "음악을 검색했습니다.", ctx.guild.name, ctx.author.name, Extra=f"제목: {Query}")
 
        # 음악 재생
        try:
            Message = await self.bot.wait_for("message", timeout=30, check=lambda M: (M.author == ctx.author
                                                                            and M.channel == ctx.channel
                                                                            and M.content.isdigit()
                                                                            and 1 <= int(M.content) <= len(Results)))
            YT = Results[int(Message.content) - 1]
            Stream = YT.streams.filter(**self.Pytubefix_Options).order_by("abr").desc().first()
            Song_Info = self.Build_Song_Info(YT, ctx)
 
            # 음악 재생 또는 대기열에 추가
            if Player.Is_Playing():
                Player.Add_To_Queue(Stream.url, Song_Info)
                Description = f"**{YT.title}** 음악을 대기열에 추가했습니다."
            else:
                Player.Suppress_Next_Start_Embed = True
                await Player.Play(Stream.url, Song_Info)
                Description = f"**{YT.title}** 음악을 재생하고 있습니다."

            Embed = await self.Build_Embed(Song_Info, ctx, Description=Description)
            return await ctx.respond(embed=Embed)
        # 시간 초과 시 스크립트
        except asyncio.TimeoutError:
            await ctx.send(embed=Error_Dialog_Embed("시간이 초과되어 동작을 실행하지 않습니다."))

    # /음악 스킵
    @Music.command(name="스킵", description="현재 재생 중인 음악을 건너 뜁니다.")
    async def Skip_Music(self, ctx):
        # 서버 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)
 
        # 재생 상태 확인
        if not Player or not Player.Is_Playing():
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)
 
        # 다음 곡이 존재하는지 확인
        if not Player.Queue and not Player.Loop:
            return await ctx.respond(embed=Error_Dialog_Embed("다음 곡을 찾을 수 없습니다."), ephemeral=True)
 
        # 음성 채널 사용자 수 감지 (애플리케이션 제외)
        Members = [M for M in ctx.voice_client.channel.members if not M.bot]
 
        # 사용자가 1명이거나 관리자이면 즉시 스킵
        if len(Members) <= 1 or ctx.author.guild_permissions.administrator:
            Player.Skip()
            return await ctx.respond(embed=Success_Dialog_Embed("재생 중인 음악을 건너뛰었습니다."))
 
        # 필요한 투표 수 계산
        Required_Votes = (len(Members) // 2) + 1
 
        # 스킵 투표 진행
        await ctx.respond(embed=discord.Embed(
            title=":white_check_mark: 이 음악을 건너 뛸까요?",
            description=(
                f"음성 채널에 사용자가 2명 이상이므로 투표를 진행합니다.\n\n"
                f"필요 찬성 수: **{Required_Votes}**\n"
                f"투표 시간: **30초**")), View = VoteView(ctx, Player, Required_Votes, Action=Player.Skip,
                Success_Message=":white_check_mark: 투표가 통과되어 재생 중인 음악을 건너뛰었습니다."))

        Print_Log("Music", "음악을 스킵했습니다.", ctx.guild.name, ctx.author.name)
    
    # /음악 정지
    @Music.command(name="정지", description="재생 중인 음악을 정지하고 대기열을 초기화합니다.")
    async def Stop_Music(self, ctx):
        # 서버 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)
 
        # 재생 상태 확인
        if not Player or not Player.Voice:
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)
        
        # 재생 중인 음악 정지
        await Player.Stop()
        self.Players.pop(ctx.guild.id, None)
 
        await ctx.respond(embed=Success_Dialog_Embed("재생 중인 음악을 정지하고 대기열을 초기화했습니다."))
        Print_Log("Music", "음악을 정지했습니다.", ctx.guild.name, ctx.author.name)

    # /음악 일시정지
    @Music.command(name="일시정지", description="재생 중인 음악을 일시정지합니다.")
    async def Pause_Music(self, ctx):
        await self.Control_Player_Action(ctx, lambda P: P.Is_Playing(), lambda P: P.Pause(), "재생 중인 음악을 일시정지했습니다.")
        Print_Log("Music", "음악을 일시정지했습니다.", ctx.guild.name, ctx.author.name)
        
    # /음악 재개
    @Music.command(name="재개", description="일시 정지한 음악을 다시 재생합니다.")
    async def Resume_Music(self, ctx):
        await self.Control_Player_Action(ctx, lambda P: P.Is_Paused(), lambda P: P.Resume(), "일시 정지한 음악을 다시 재생했습니다.")
        Print_Log("Music", "음악을 재개했습니다.", ctx.guild.name, ctx.author.name)

    # /음악 반복
    @Music.command(name="반복", description="현재 음악을 반복할 옵션을 선택합니다.")
    async def Loop_Music(self, ctx, Mode: discord.Option(str, name="모드", description="반복 모드", choices=["대기열", "단일", "끄기"], required=True)):
        # 서버 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)
 
        # 재생 상태 확인
        if not Player or not Player.Is_Playing():
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)
 
        # 반복 모드 정의
        Modes = {
            "대기열": (True, False, "반복 모드를 **대기열 반복**으로 설정했습니다."),
            "단일": (False, True, "반복 모드를 **단일 반복**으로 설정했습니다."),
            "끄기": (False, False, "반복 모드를 **해제**했습니다.")
        }

        # 반복 모드 설정
        Player.Loop, Player.Loop_Queue, Message = Modes[Mode]
        await ctx.respond(embed=Success_Dialog_Embed(Message))
        Print_Log("Music", "음악 반복 모드를 설정했습니다.", ctx.guild.name, ctx.author.name, Extra=f"모드: {Mode}")

    # /음악 이전곡
    @Music.command(name="이전곡", description="이전 곡을 다시 재생합니다.")
    async def Previous_Music(self, ctx):
        # 서버 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)
 
        # 재생 상태 확인
        if not Player or not Player.Current:
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)
 
        # 이전 곡이 존재하는지 확인
        if not Player.History:
            return await ctx.respond(embed=Error_Dialog_Embed("이전 곡을 찾을 수 없습니다."), ephemeral=True)
        
        # 이전 곡 정보 가져오기
        Prev_Title = Player.History[-1]["Info"]["Title"]
 
        # 이전 곡 재생 함수
        async def Play_Previous():
            Player.Suppress_Next_Start_Embed = True
            await Player.Play_Previous()

        # 음성 채널 사용자 수 계산 (애플리케이션 제외)
        Members = [M for M in ctx.voice_client.channel.members if not M.bot]
 
        # 사용자가 1명이거나 관리자이면 즉시 이전 곡 재생
        if len(Members) <= 1 or ctx.author.guild_permissions.administrator:
            await Play_Previous()
            return await ctx.respond(embed=Success_Dialog_Embed(f"**{Prev_Title}** 음악을 재생합니다."))
 
        # 필요한 투표 수 계산
        Required_Votes = (len(Members) // 2) + 1
 
        # 이전 곡 재생 투표 진행
        await ctx.respond(embed=discord.Embed(
            title=":white_check_mark: 이전 곡을 재생할까요?",
            description=(
                f"음성 채널에 사용자가 2명 이상이므로 투표를 진행합니다.\n\n"
                f"필요 찬성 수: **{Required_Votes}**\n"
                f"투표 시간: **30초**")), View=VoteView(ctx, Player, Required_Votes, Action=Play_Previous,
                Success_Message=f":white_check_mark: 투표가 통과되어 **{Prev_Title}** 음악을 재생합니다."))
 
    # /음악 정보
    @Music.command(name="정보", description="현재 재생 중인 음악의 정보를 표시합니다.")
    async def Now_Music(self, ctx):
        # 서버 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)
 
        # 재생 상태 확인
        if not Player or not Player.Is_Playing():
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)
        
        # 현재 재생 중인 음악 정보 가져오기
        Song = Player.Current["Info"]
        await ctx.respond(embed=await self.Build_Embed(Song, ctx, f"**{Song['Title']}** 음악을 재생하고 있습니다."))
        Print_Log("Music", "음악 정보를 표시했습니다.", ctx.guild.name, ctx.author.name)
 
    # /음악 볼륨
    @Music.command(name="볼륨", description="음악의 볼륨을 조절합니다.")
    async def Set_Volume_Music(self, ctx, Value: discord.Option(int, name="크기", description="볼륨 크기 (0 ~ 500)", required=True)):
        # 서버 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)
 
        # 재생 상태 확인
        if not Player or not Player.Voice:
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)
 
        # 볼륨 범위 확인
        if not 0 <= Value <= 500:
            return await ctx.respond(embed=Error_Dialog_Embed("볼륨은 0 이상 500 이하의 정수여야 합니다."), ephemeral=True)
 
        # 볼륨 조절
        Player.Set_Volume(Value / 100)
        await ctx.respond(embed=Success_Dialog_Embed(f"애플리케이션의 볼륨을 **{Value}%** 로 설정했습니다."))
        Print_Log("Music", "음악의 볼륨을 조절했습니다.", ctx.guild.name, ctx.author.name, Extra=f"볼륨: {Value}%")

    Queue = Music.create_subgroup("대기열", "대기열 관련 명령어입니다.")

    # /음악 대기열 목록
    @Queue.command(name="목록", description="대기열을 표시합니다.")
    async def Queue_List(self, ctx):
        # 서버 별 플레이어 지정
        Player = self.Check_Queue(ctx)
 
        # 재생 상태 확인
        if not Player:
            return
 
        # 대기열 페이지 생성 및 표시
        Embed, _ = self.Queue_Page(ctx, Player, 1)
        await ctx.respond(embed=Embed, view=QueueView(ctx, Player, self.Queue_Page))
        Print_Log("Music", "대기열을 표시했습니다.", ctx.guild.name, ctx.author.name)

    # /음악 대기열 초기화
    @Queue.command(name="초기화", description="대기열을 초기화합니다.")
    async def Queue_Clear(self, ctx):
        # 서버 별 플레이어 지정
        Player = self.Check_Queue(ctx)
 
        # 재생 상태 확인
        if not Player:
            return
 
        # 삭제된 곡 수 계산
        Cleared_Count = len(Player.Queue)

        # 대기열 초기화
        Player.Queue.clear()
        await ctx.respond(embed=Success_Dialog_Embed(f"대기열을 초기화했습니다. (삭제된 음악 개수: {Cleared_Count}개)"))
        Print_Log("Music", "대기열을 초기화했습니다.", ctx.guild.name, ctx.author.name, Extra=f"삭제된 음악 개수: {Cleared_Count}개")

    # /음악 대기열 삭제 [번호]
    @Queue.command(name="삭제", description="대기열에서 음악을 삭제합니다.")
    async def Queue_Delete(self, ctx, Position: discord.Option(int, name="번호", description="삭제할 음악의 번호", required=True)):
        # 서버 별 플레이어 지정
        Player = self.Check_Queue(ctx)
 
        # 재생 상태 확인
        if not Player:
            return
 
        # 대기열 범위 확인
        if not 1 <= Position <= len(Player.Queue):
            return await ctx.respond(embed=Error_Dialog_Embed(f"올바른 번호를 입력하세요. (1 ~ {len(Player.Queue)})"), ephemeral=True)
 
        # 대기열에서 음악 삭제
        Removed = Player.Queue.pop(Position - 1)
        await ctx.respond(embed=Success_Dialog_Embed(f"**{Removed['Info']['Title']}** 음악을 대기열에서 삭제했습니다."))
        Print_Log("Music", "대기열에서 음악을 삭제했습니다.", ctx.guild.name, ctx.author.name)

    # /음악 대기열 재생 [번호]
    @Queue.command(name="재생", description="대기열에서 원하는 번호의 음악을 바로 재생합니다.")
    async def Queue_Play(self, ctx, Num: discord.Option(int, name="번호", description="재생할 음악의 번호", required=True)):
        # 서버 별 플레이어 지정
        Player = self.Check_Queue(ctx)
 
        # 재생 상태 확인
        if not Player:
            return
 
        # 대기열 범위 확인
        if not 1 <= Num <= len(Player.Queue):
            return await ctx.respond(embed=Error_Dialog_Embed(f"올바른 번호를 입력하세요. (1 ~ {len(Player.Queue)})"), ephemeral=True)

        # 대기열에서 음악 정보 가져오기
        Song = Player.Queue[Num - 1]
        Title = Song["Info"]["Title"]

        # 음악 재생 함수
        async def Play():
            Player.Suppress_Next_Start_Embed = True
            return await Player.Play_From_Queue(Num)

        # 음성 채널 사용자 수 감지 (애플리케이션 제외)
        Voice = ctx.voice_client
        Members = [M for M in Voice.channel.members if not M.bot] if Voice else []

        # 사용자가 1명이거나 관리자이면 즉시 곡 재생
        if len(Members) <= 1 or ctx.author.guild_permissions.administrator:
            if not await Play():
                return await ctx.respond(embed=Error_Dialog_Embed("음악을 재생하지 못했습니다."), ephemeral=True)

            return await ctx.respond(embed=Success_Dialog_Embed(f"**{Title}** 음악을 재생합니다."))

        # 필요한 투표 수 계산
        Required_Votes = (len(Members) // 2) + 1

        # 투표 진행
        await ctx.respond(embed=discord.Embed(
            title=f":white_check_mark: **{Title}** 음악을 재생할까요?",
            description=(
                f"음성 채널에 사용자가 2명 이상이므로 투표를 진행합니다.\n\n"
                f"필요 찬성 수: **{Required_Votes}**\n"
                f"투표 시간: **30초**")), view = VoteView(ctx, Player, Required_Votes, Action=Play,
                Success_Message=f":white_check_mark: 투표가 통과되어 **{Title}** 음악을 재생합니다."))

        Print_Log("Music", "대기열에서 음악을 재생했습니다.", ctx.guild.name, ctx.author.name)

    # /음악 대기열 셔플
    @Queue.command(name="셔플", description="대기열을 셔플합니다.")
    async def Queue_Shuffle(self, ctx):
        # 서버 별 플레이어 지정
        Player = self.Check_Queue(ctx)
 
        # 재생 상태 확인
        if not Player:
            return

        # 대기열 셔플
        if not await Player.Shuffle_Queue():
            return await ctx.respond(embed=Error_Dialog_Embed("대기열에 2개 이상의 곡을 추가해 주세요."), ephemeral=True)

        await ctx.respond(embed=Success_Dialog_Embed("대기열을 셔플했습니다."))
        Print_Log("Music", "대기열을 셔플했습니다.", ctx.guild.name, ctx.author.name)

def setup(bot):
    bot.add_cog(Music(bot))