import discord
import datetime
import re
import asyncio
import random
from discord.ext import commands
from pytubefix import YouTube, Search, Playlist
from Resources import Success_Dialog_Embed, Error_Dialog_Embed, Print_Log

# URL 체크 스크립트
def Check_YT_URL(text: str) -> bool:
    return re.match(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/", text) is not None

# 재생 목록 URL 체크 스크립트
def Check_Playlist_URL(url: str) -> bool:
    return "list=" in url

# MusicPlayer 클래스
class MusicPlayer:
    def __init__(self, bot, FFMPEG_Options: dict):
        self.bot = bot
        self.FFMPEG_Options = FFMPEG_Options
        self.Voice: discord.VoiceClient | None = None
        self.Queue: list[dict] = []
        self.History: list[dict] = []
        self.Current: dict | None = None
        self.Lock = asyncio.Lock()
        self.Loop = False
        self.Loop_Queue = False
        self.On_Song_Start = None
        self.Suppress_Next_Start_embed = False
        self.Volume = 1.0
        self.Manual_Stop = False

    # 음악 재생 상태 확인 스크립트
    def Is_Playing(self) -> bool:
        return self.Voice is not None and self.Voice.is_playing()

    # 음악 일시 정지 상태 확인 스크립트
    def Is_Paused(self) -> bool:
        return self.Voice is not None and self.Voice.is_paused()

    # 음악 재생 스크립트
    async def Play(self, Stream_URL: str, Song_Info: dict):
        async with self.Lock:
            try:
                Source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(Stream_URL, **self.FFMPEG_Options), volume=self.Volume)
                self.Current = {"url": Stream_URL, "info": Song_Info}

                if self.On_Song_Start and not self.Suppress_Next_Start_Embed and not self.Loop and not self.Loop_Queue:
                    await self.On_Song_Start(Song_Info)

                self.Suppress_Next_Start_embed = False

                self.Voice.play(Source, after=lambda Error: self.Bot.loop.create_task(self.After_Play(Error)))

            except Exception as Error:
                Print_Log("Music", "음악을 재생하는 중 오류가 발생했습니다.", "시스템", "시스템", extra=f"({Error})")

    # 음악 종료 후 스크립트
    async def After_Play(self, Error):
        if Error:
            Print_Log("Music", "FFmpeg 오류가 발생했습니다.", "시스템", "시스템", extra=f"({Error})")

        if self.Manual_Stop:
            self.Manual_Stop = False
            return

        # 단일 반복
        if self.Loop and self.Current:
            return await self.Play(self.Current["url"], self.Current["info"])

        # 이전 곡 저장
        if self.Current:
            self.History.append(self.Current)

            # 대기열 반복
            if self.Loop_Queue:
                self.Queue.append(self.Current)

        await self.Play_Next()

    # 다음 곡 재생 스크립트
    async def Play_Next(self):
        if not self.Queue:
            self.Current = None

            if self.Voice and self.Voice.is_connected():
                await self.Voice.disconnect()

            self.Voice = None
            return

        Next_Song = self.Queue.pop(0)

        await self.Play(Next_Song["url"], Next_Song["info"])

    # 대기열에 음악 추가 스크립트
    def Add_to_Queue(self, Stream_URL: str, Song_Info: dict):
        self.Queue.append({"url": Stream_URL, "info": Song_Info})

    # 이전 음악 재생 스크립트
    async def Play_Previous(self):
        if not self.History:
            return False

        Previous_Song = self.History.pop()
        Previous_Loop = self.Loop
        Previous_Loop_Queue = self.Loop_Queue

        self.Loop = False
        self.Loop_Queue = False
        self.Manual_Stop = True

        # 현재 음악을 대기열 앞으로 이동
        if self.Current:
            self.Queue.insert(0, self.Current)

        if self.Voice and (self.Voice.is_playing() or self.Voice.is_paused()):
            self.Voice.stop()

        await self.Play(Previous_Song["url"], Previous_Song["info"])

        self.Loop = Previous_Loop
        self.Loop_Queue = Previous_Loop_Queue

        return True

    # 음악 일시 정지 스크립트
    def Pause(self):
        if self.Is_Playing():
            self.Voice.pause()

    # 음악 재개 스크립트
    def Resume(self):
        if self.Is_Paused():
            self.Voice.resume()

    # 음악 스킵 스크립트
    def Skip(self):
        if self.Voice and (self.Voice.is_playing() or self.Voice.is_paused()):
            self.Voice.stop()

    # 음악 정지 스크립트
    async def Stop(self):
        self.Queue.clear()
        self.History.clear()
        self.Current = None

        if not self.Voice:
            return

        try:
            if self.Voice.is_playing() or self.Voice.is_paused():
                self.Voice.stop()

            if self.Voice.is_connected():
                await self.Voice.disconnect()

        except Exception as Error:
            Print_Log("Music", "음성 연결 종료 중 오류가 발생했습니다.", "시스템", "시스템", extra=f"({Error})")

        self.Voice = None

    # 볼륨 조절 스크립트
    def Set_Volume(self, Volume: float):
        self.Volume = max(0.0, min(Volume, 5.0))

        if self.Voice and self.Voice.source and hasattr(self.Voice.source, "volume"):
            self.Voice.source.volume = self.Volume

    # 대기열 음악 바로 재생 스크립트
    async def Play_From_Queue(self, Position: int):
        if Position < 1 or Position > len(self.Queue):
            return False

        Selected_Song = self.Queue.pop(Position - 1)

        # 현재 곡 저장
        if self.Current:
            self.History.append(self.Current)

            # 대기열 반복 중이면 현재 곡 유지
            if self.Loop_Queue:
                self.Queue.append(self.Current)

        self.Manual_Stop = True

        if self.Voice and (self.Voice.is_playing() or self.Voice.is_paused()):
            self.Voice.stop()

        await self.Play(Selected_Song["url"], Selected_Song["info"])

        return True

    # 대기열 셔플 스크립트
    async def Shuffle_Queue(self):
        if len(self.Queue) < 2:
            return False

        random.shuffle(self.Queue)
        return True

# 대기열 뷰 클래스
class QueueView(discord.ui.View):
    Songs_Per_Page = 10

    def __init__(self, ctx, Player, Queue_Page_Callback):
        super().__init__(timeout=120)

        self.ctx = ctx
        self.Player = Player
        self.Queue_Page_Callback = Queue_Page_Callback
        self.Page = 1

        self.Update_QueueButtons()

    # 총 페이지 수 반환
    @property
    def Total_Pages(self) -> int:
        return max(1, (len(self.Player.Queue) + self.Songs_Per_Page - 1) // self.Songs_Per_Page)

    # 버튼 업데이트
    def Update_QueueButtons(self):
        self.clear_items()

        Buttons = [
            ("⏪", self.Page > 1, self.Queue_First),
            ("⬅️", self.Page > 1, self.Queue_Previous),
            ("➡️", self.Page < self.Total_Pages, self.Queue_Next),
            ("⏩", self.Page < self.Total_Pages, self.Queue_Last)
        ]

        for Emoji, Enabled, Callback in Buttons:
            self.add_item(self.NavigationButton(Emoji, Enabled, Callback))

    # 메세지 업데이트
    async def Update_QueueView(self, interaction: discord.Interaction):
        Embed, _ = self.Queue_Page_Callback(self.ctx, self.Player, self.Page)

        self.Update_QueueButtons()

        await interaction.response.edit_message(embed=embed, view=self)

    # 버튼 클래스
    class NavigationButton(discord.ui.Button):
        def __init__(self, Emoji: str, Enabled: bool, Callback):
            super().__init__(style=discord.ButtonStyle.secondary, emoji=Emoji, disabled=not Enabled)

            self.CallbackFunc = Callback

        async def callback(self, interaction: discord.Interaction):
            await self.CallbackFunc(interaction)

    # 첫 페이지
    async def Queue_First(self, interaction: discord.Interaction):
        self.Page = 1
        await self.Update_QueueView(interaction)

    # 이전 페이지
    async def Queue_Previous(self, interaction: discord.Interaction):
        self.Page = max(1, self.Page - 1)
        await self.Update_QueueView(interaction)

    # 다음 페이지
    async def Queue_Next(self, interaction: discord.Interaction):
        self.Page = min(self.Total_Pages, self.Page + 1)
        await self.Update_QueueView(interaction)

    # 마지막 페이지
    async def Queue_Last(self, interaction: discord.Interaction):
        self.Page = self.Total_Pages
        await self.Update_QueueView(interaction)

    # View 타임아웃
    async def on_timeout(self):
        for Item in self.children:
            Item.disabled = True

        try:
            await self.message.edit(view=self)
        except:
            pass

# 투표 뷰 클래스
class VoteView(discord.ui.View):
    def __init__(self, ctx, Player, RequiredVotes: int, Action, SuccessMessage: str):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.Player = Player
        self.RequiredVotes = RequiredVotes
        self.Action = Action
        self.SuccessMessage = SuccessMessage
        self.Votes: set[int] = set()

    # 투표 버튼
    @discord.ui.button(label="투표하기", style=discord.ButtonStyle.danger)
    async def Vote(self, Button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.bot:
            return

        VoiceState = self.ctx.author.voice

        if (not VoiceState or interaction.user not in VoiceState.channel.members):
            return await interaction.response.send_message(embed=Error_Dialog_Embed("음성 채널에 있는 사용자만 투표할 수 있습니다."), ephemeral=True)

        if interaction.user.id in self.Votes:
            return await interaction.response.send_message(embed=Error_Dialog_Embed("이미 투표하셨습니다."), ephemeral=True)

        self.Votes.add(interaction.user.id)

        # 투표 통과
        if len(self.Votes) >= self.RequiredVotes:
            await self.Action()
            self.stop()
            return await interaction.response.edit_message(embed=Success_Dialog_Embed(self.SuccessMessage.replace(":white_check_mark: ", "")), view=None)

        # 투표 진행
        await interaction.response.edit_message(embed=discord.Embed(description=("투표가 진행 중입니다.\n" f"찬성: **{len(self.Votes)} / {self.RequiredVotes}**")),view=self)

    # View 타임아웃
    async def on_timeout(self):
        for Item in self.children:
            Item.disabled = True

        try:
            await self.message.edit(view=self)
        except:
            pass


# 재생목록 추가 뷰 클래스
class PlaylistConfirmView(discord.ui.View):
    def __init__(self, Author, Playlist_URL: str, Player):
        super().__init__(timeout=30)
        self.Author = Author
        self.Playlist_URL = Playlist_URL
        self.Player = Player
        self.Value: bool | None = None

    # 인터랙션 사용자 확인
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.Author:
            await interaction.response.send_message(embed=Error_Dialog_Embed("이 버튼을 조작할 권한이 없습니다."), ephemeral=True)
            return False

        return True

    # 재생목록 추가
    @discord.ui.button(label="추가하기", style=discord.ButtonStyle.green)
    async def Confirm(self, Button: discord.ui.Button, interaction: discord.Interaction):
        self.Value = True
        await interaction.response.defer()
        self.DisableAllItems()
        self.stop()

    # 재생목록 취소
    @discord.ui.button(label="취소", style=discord.ButtonStyle.red)
    async def Cancel(self, Button: discord.ui.Button, interaction: discord.Interaction):
        self.Value = False
        await interaction.response.defer()
        self.DisableAllItems()
        self.stop()

    # 모든 버튼 비활성화
    def DisableAllItems(self):
        for Item in self.children:
            Item.disabled = True

    # 시간 초과
    async def on_timeout(self):
        self.DisableAllItems()

        try:
            await self.message.edit(view=self)
        except:
            pass

class Music(commands.Cog):
    FFMPEG_Options = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn"
    }

    PYTUBEFIX_Options = {
        "only_audio": True,
        "abr": "160kbps"
    }

    def __init__(self, bot):
        self.bot = bot
        self.Players: dict[int, MusicPlayer] = {}

    # 애플리케이션 자동 퇴장
    @discord.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after):
        if member.bot:
            return

        Player = self.Players.get(member.guild.id)

        if not Player or not Player.voice:
            return

        Channel = Player.voice.channel

        if not Channel:
            return

        Members = [Member for Member in Channel.members if not Member.bot]

        # 멤버가 없으면 자동으로 정지
        if not Members:
            await Player.stop()
            self.Players.pop(member.guild.id, None)

    # 음악 정보 생성
    def Build_Song_Info(self, yt, ctx) -> dict:
        return {
            "title": yt.title,
            "url": yt.watch_url,
            "webpage_url": yt.watch_url,
            "duration": yt.length,
            "uploader": yt.author,
            "thumbnail": yt.thumbnail_url,
            "requester": ctx.author.display_name,
            "text_channel": ctx.channel
        }

    # 음악 길이 포맷
    def Format_Song_Duration(self, Seconds: int | None) -> str:
        if Seconds is None:
            return "알 수 없음"

        Minutes, Seconds = divmod(Seconds, 60)
        Hours, Minutes = divmod(Minutes, 60)

        if Hours:
            return f"{Hours}:{Minutes:02d}:{Seconds:02d}"

        return f"{Minutes}:{Seconds:02d}"

    # Embed 생성
    def Build_Embed(self, Song_Info: dict, Description: str) -> discord.Embed:
        embed = discord.Embed(
            title=f"🎵 {Song_Info['title']}",
            description=Description,
            url=Song_Info.get("webpage_url"),
            color=discord.Color.blue()
        )
        embed.add_field(name="영상 길이", Value=self.Format_Song_Duration(Song_Info["duration"]), inline=True)
        embed.add_field(name="채널", Value=Song_Info["uploader"], inline=True)
        embed.set_thumbnail(url=Song_Info["thumbnail"])
        embed.set_footer(text=f"요청자 : {Song_Info['requester']}")

        return embed

    # 음악 시작 시 Embed 전송
    async def Send_Embed(self, Song_Info: dict):
        Channel = Song_Info.get("text_channel")

        if not Channel:
            return

        embed = self.Build_Embed(Song_Info,f"**{Song_Info['title']}** 음악을 재생하고 있습니다.")

        await Channel.send(embed=embed)

    # 대기열 페이지 생성
    def Build_Queue_Page(self, ctx, Player: MusicPlayer, Page_Number: int):
        Queue = Player.Queue
        Start_Index = (Page_Number - 1) * self.Songs_Per_Page
        End_Index = min(Start_Index + self.Songs_Per_Page, len(Queue))

        if Start_Index >= len(Queue):
            return None, None

        embed = discord.Embed(title="🎶 대기열을 표시합니다.", description="현재 대기열 목록:", color=discord.Color.blue())

        # 현재 곡
        if Player.Current:
            CurrentInfo = Player.Current["info"]

            embed.add_field(
                name=f"현재 재생 중: {CurrentInfo['title']}",
                Value=f"길이: {self.Format_Song_Duration(CurrentInfo['duration'])} | 요청자: {CurrentInfo['requester']}",
                inline=False
            )

        # 대기열
        for Index in range(Start_Index, End_Index):
            Info = Queue[Index]["info"]

            embed.add_field(
                name=f"{Index + 1}. {Info['title']}",
                Value=f"길이: {self.Format_Song_Duration(Info['duration'])} | 요청자: {Info['requester']}",
                inline=False
            )

        Total_Pages = max(1, (len(Queue) + self.Songs_Per_Page - 1) // self.Songs_Per_Page)

        embed.set_footer(text=f"페이지 {Page_Number} / {Total_Pages}")

        return embed, Total_Pages

    # 재생목록 추가
    async def Add_Playlist(self, URL: str, ctx, Player: MusicPlayer):
        PlaylistData = Playlist(URL)
        Videos = list(PlaylistData.videos)

        Added_Count = 0

        for yt in Videos[1:]:
            try:
                Stream = (yt.streams.filter(**self.PYTUBEFIX_Options).order_by("abr").desc().first())

                if not Stream:
                    continue

                Song_Info = self.Build_Song_Info(yt, ctx)

                Player.Add_to_Queue(Stream.url, Song_Info)

                Added_Count += 1

            except Exception as Error:
                Print_Log("Music", "재생목록을 추가하는 중 오류가 발생했습니다.", "시스템", "시스템", extra=f"({Error})")

        await ctx.respond(embed=Success_Dialog_Embed(f"재생목록에서 **{Added_Count}곡**을 대기열에 추가했습니다."))

    # 음성 채널 연결
    async def Ensure_Voice(self, ctx, Player: MusicPlayer) -> bool:
        if not ctx.author.voice:
            await ctx.respond(embed=Error_Dialog_Embed("먼저 음성 채널에 연결해주세요."), ephemeral=True)
            return False

        Channel = ctx.author.voice.channel

        # 다른 채널 사용 중
        if ctx.voice_client and ctx.voice_client.channel != Channel:
            await ctx.respond(embed=Error_Dialog_Embed("애플리케이션이 같은 서버의 다른 음성 채널에서 재생 중입니다. 연결을 끊거나 기다린 후 다시 시도하세요."), ephemeral=True)
            return False

        # 연결
        if not ctx.voice_client:
            Player.Voice = await Channel.connect()
        else:
            Player.Voice = ctx.voice_client

        return True

    # 음악 명령어 그룹
    Music_CMDGroup = discord.SlashCommandGroup("음악")

    # /음악 재생 [제목 / URL]
    @Music_CMDGroup.command(name="재생", description="YouTube에서 음악을 찾아 재생합니다.")
    async def Play(self, ctx, url: discord.Option(str, name="제목", description="재생할 음악의 제목 또는 URL을 입력하세요.", required=True)):
        Print_Log("Music", "재생 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name, extra=f"제목 / URL: {url}")
        await ctx.defer()

        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player:
            Player = MusicPlayer(self.bot, self.FFMPEG_Options)
            self.Players[ctx.guild.id] = Player

        Player.On_Song_Start = self.Send_Embed

        # 음성 채널 입장
        if not await self.Ensure_VC(ctx, Player):
            return

        # 재생 목록 URL 체크
        if Check_Playlist_URL(url):
            Playlist = Playlist(url)
            Videos = list(Playlist.videos)
            View = PlaylistConfirmView(ctx.author, url, Player)

            First_Video = Videos[0]
            First_Stream = First_Video.streams.filter(**self.PYTUBEFIX_Options).order_by("abr").desc().first()
            First_Info = self.Build_Song_Info(First_Video, ctx, Queue_Position=len(Player.Queue) + 1)

            if Player.Is_Playing():
                Player.Add_to_Queue(First_Stream.url, First_Info)
            else:
                Player.Suppress_Next_Start_embed = True
                await Player.Play(First_Stream.url, First_Info)
                embed = await self.Build_Embed(First_Info, ctx, description=f"**{First_Info['title']}** 음악을 재생하고 있습니다.")
                await ctx.respond(embed=embed)

            embed = discord.Embed(title="📃 재생목록 링크를 감지했습니다.", description="이 재생목록의 모든 곡을 대기열에 추가할까요?")
            Message = await ctx.followup.send(embed=embed, view=View)
            await View.wait()

            for item in View.children:
                item.disabled = True
            await Message.edit(view=View)

            if View.Value is None:
                return await ctx.followup.send(embed=Error_Dialog_Embed("시간이 초과되어 동작을 실행하지 않습니다."), ephemeral=True)

            if not View.Value:
                return await ctx.followup.send(embed=Success_Dialog_Embed("재생목록의 곡을 추가하지 않았습니다."), ephemeral=True)

            return await self.Add_Playlist_to_Queue(url, ctx, Player)

        # URL 체크
        if Check_YouTube_URL(url):
            YouTube = YouTube(url)
        else:
            Search = Search(url)
            if not Search.results:return await ctx.respond(embed=Error_Dialog_Embed("검색 결과를 찾을 수 없습니다."), ephemeral=True)
            YouTube = Search.results[0]

        # 곡 정보 저장
        Stream = YouTube.streams.filter(**self.PYTUBEFIX_Options).order_by("abr").desc().first()
        Song_Info = self.Build_Song_Info(YouTube, ctx, Queue_Position=len(Player.Queue) + 1)

        # 곡 재생
        if Player.Is_Playing():
            Player.Add_to_Queue(Stream.url, Song_Info)
            embed = await self.Build_Embed(Song_Info, ctx, description=f"**{YouTube.title}** 음악을 대기열에 추가했습니다.")
            Print_Log("Music", "대기열에 곡을 추가했습니다.", ctx.guild.name, ctx.author.name, YouTube.title)
            return await ctx.respond(embed=embed)
        else:
            Player.Suppress_Next_Start_embed = True
            await Player.Play(Stream.url, Song_Info)
            embed = await self.Build_Embed(Song_Info, ctx, description=f"**{YouTube.title}** 음악을 재생하고 있습니다.")
            return await ctx.respond(embed=embed)

    # /음악 검색 [제목] [개수]
    @Music_CMDGroup.command(name="검색", description="YouTube에서 음악을 지정한 개수만큼 검색합니다.")
    async def Search_Music(self, ctx,
        query: discord.Option(str, name="제목", description="검색할 음악의 제목", required=True),
        index: discord.Option(int, name="개수", description="검색할 개수 (1 ~ 10, 선택)", required=False, min_value=1, max_value=10, default=5)):
        Print_Log("Music", "검색 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name, extra=f"제목: {query}, 개수: {index}")
        await ctx.defer()
        
        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)
        
        if not Player:
            Player = MusicPlayer(self.bot, self.FFMPEG_Options)
            self.Players[ctx.guild.id] = Player

        Player.On_Song_Start = self.Send_Embed

        # 음성 채널 입장
        if not await self.Ensure_VC(ctx, Player):
            return
        
        # 검색
        Search = Search(query)
        Results = Search.results[:index]

        if not Search.results:
            return await ctx.respond(embed=Error_Dialog_Embed("검색 결과가 없습니다."), ephemeral=True)

        # 검색 결과 표시
        embed = discord.Embed(title=f"🎶 '{query}'에 대한 검색 결과", color=discord.Color.blue())

        for i, yt in enumerate(Results, start=1):
            Duration = self.Format_Song_Duration(yt.length) if yt.length else "알 수 없음"
            embed.add_field(name=f"{i}. {yt.title}", Value=f"채널: {yt.author}\n길이: {Duration}", inline=False)

        await ctx.respond(content="> :white_check_mark: 30초 내에 번호를 입력하여 해당 음악을 재생할 수 있습니다.", embed=embed)

        def check(m):
            return (m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= len(Results))

        # 음악 재생
        try:
            Message = await self.bot.wait_for("message", check=check, timeout=30)
            Index = int(Message.content) - 1
            YouTube = Results[Index]
            Stream = YouTube.streams.filter(**self.PYTUBEFIX_Options).order_by("abr").desc().first()
            Song_Info = self.Build_Song_Info(YouTube, ctx, queue_position=len(Player.Queue) + 1)

            if Player.Is_Playing():
                Player.Add_to_Queue(Stream.url, Song_Info)
                embed = await self.Build_Embed(Song_Info, ctx, description=f"**{YouTube.title}** 음악을 대기열에 추가했습니다.")
                return await ctx.respond(embed=embed)
            else:
                Player.Suppress_Next_Start_embed = True
                await Player.Play(Stream.url, Song_Info)
                embed = await self.Build_Embed(Song_Info, ctx, description=f"**{YouTube.title}** 음악을 재생하고 있습니다.")
                return await ctx.respond(embed=embed)

        # 시간 초과 시 스크립트
        except asyncio.TimeoutError:
            await ctx.send(embed=Error_Dialog_Embed("시간이 초과되어 동작을 실행하지 않습니다."))

    # /음악 스킵
    @Music_CMDGroup.command(name="스킵", description="현재 재생 중인 곡을 건너 뜁니다.")
    async def Skip(self, ctx):
        Print_Log("Music", "스킵 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name)
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Is_Playing():
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)

        if not Player.Queue and not Player.Loop:
            return await ctx.respond(embed=Error_Dialog_Embed("다음 곡을 찾을 수 없습니다."), ephemeral=True)

        voice = ctx.voice_client
        if not voice or not voice.channel:
            return

        members = [m for m in voice.channel.members if not m.bot]   # 음성 채널 사용자 수 감지 (애플리케이션 제외)

        # 사용자가 1명이거나 관리자이면 즉시 스킵
        if len(members) <= 1 or ctx.author.guild_permissions.administrator:
            Player.skip()
            return await ctx.respond(embed=Success_Dialog_Embed("재생 중인 음악을 건너뛰었습니다."))

        required_votes = (len(members) // 2) + 1    # 필요한 투표 수 계산

        # 스킵 투표 진행
        embed = discord.Embed(
            title=":white_check_mark: 이 음악을 건너 뛸까요?",
            description=(
                f"음성 채널에 사용자가 2명 이상이므로 투표를 진행합니다.\n\n"
                f"필요 찬성 수: **{required_votes}**\n"
                f"투표 시간: **30초**"))
        View = VoteView(ctx, Player, required_votes, action=Player.Skip, success_message=":white_check_mark: 투표가 통과되어 재생 중인 음악을 건너뛰었습니다.")
        await ctx.respond(embed=embed, view=View)

    # /음악 정지
    @Music_CMDGroup.command(name="정지", description="재생 중인 음악을 정지하고 대기열을 초기화합니다.")
    async def Stop_Song(self, ctx):
        Print_Log("Music", "정지 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name)
        
        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Voice:
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)
        
        await Player.Stop()
        self.Players.pop(ctx.guild.id, None)
        await ctx.respond(embed=Success_Dialog_Embed("재생 중인 음악을 정지하고 대기열을 초기화했습니다."))

    # /음악 일시정지
    @Music_CMDGroup.command(name="일시정지", description="재생 중인 음악을 일시정지합니다.")
    async def Pause_Song(self, ctx):
        Print_Log("Music", "일시정지 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name)

        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Is_Playing():
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)

        Player.Pause()
        await ctx.respond(embed=Success_Dialog_Embed("재생 중인 음악을 일시정지했습니다."))
        
    # /음악 재개
    @Music_CMDGroup.command(name="재개", description="일시 정지한 음악을 다시 재생합니다.")
    async def Resume_Song(self, ctx):
        Print_Log("Music", "재개 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name)
        
        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Is_Paused():
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)

        Player.Resume()
        await ctx.respond(embed=Success_Dialog_Embed("일시 정지한 음악을 다시 재생했습니다."))

    # /음악 반복 [모드]
    @Music_CMDGroup.command(name="반복", description="현재 음악을 반복할 옵션을 선택합니다.")
    async def Loop(self, ctx,
        mode: discord.Option(str, name="모드", description="반복 모드", choices=["대기열", "단일", "끄기"], required=True)):
        Print_Log("Music", "반복 설정 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name, extra=f"모드: {mode}")
        
        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Is_Playing():
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)

        # 모드가 대기열 반복이라면
        if mode == "대기열":
            Player.Loop_Queue = True
            Player.Loop = False
            await ctx.respond(embed=Success_Dialog_Embed("반복 모드를 **대기열 반복**으로 설정했습니다."))

        # 모드가 단일 반복이라면
        elif mode == "단일":
            Player.Loop = True
            Player.Loop_Queue = False
            await ctx.respond(embed=Success_Dialog_Embed("반복 모드를 **단일 반복**으로 설정했습니다."))

        # 모드가 끄기라면
        elif mode == "끄기":
            Player.Loop = False
            Player.Loop_Queue = False
            await ctx.respond(embed=Success_Dialog_Embed("반복 모드를 **해제**했습니다."))

    # /음악 이전곡
    @Music_CMDGroup.command(name="이전곡", description="이전 곡을 다시 재생합니다.")
    async def Previous_Song(self, ctx):
        Print_Log("Music", "이전 곡 재생 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name)

        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Current:
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)

        if not Player.History:
            return await ctx.respond(embed=Error_Dialog_Embed("이전 곡을 찾을 수 없습니다."), ephemeral=True)
        
        Prev_Info = Player.history[-1]["info"]
        Prev_Title = Prev_Info["title"]

        Voice = ctx.voice_client
        if not Voice or not Voice.channel:
            return

        # 음성 채널 사용자 수 감지 (애플리케이션 제외)
        Members = [m for m in Voice.channel.members if not m.bot]

        # 사용자가 1명이거나 관리자이면 즉시 이전 곡 재생
        if len(Members) <= 1 or ctx.author.guild_permissions.administrator:
            Player.Suppress_Next_Start_embed = True
            await Player.Play_Previous()
            return await ctx.respond(embed=Success_Dialog_Embed(f"**{Prev_Title}** 음악을 재생합니다."))

        # 필요한 투표 수 계산
        Required_Votes = (len(Members) // 2) + 1

        # 이전 곡 재생 투표 진행
        embed = discord.Embed(
            title=":white_check_mark: 이전 곡을 재생할까요?",
            description=(
                f"음성 채널에 사용자가 2명 이상이므로 투표를 진행합니다.\n\n"
                f"필요 찬성 수: **{Required_Votes}**\n"
                f"투표 시간: **30초**"))
        
        async def action():
            Player.Suppress_Next_Start_embed = True
            await Player.Play_Previous()
            
        View = VoteView(ctx, Player, Required_Votes, action=action, success_message=f":white_check_mark: 투표가 통과되어 **{Prev_Title}** 음악을 재생합니다.")
        await ctx.respond(embed=embed, view=View)

    # /음악 정보
    @Music_CMDGroup.command(name="정보", description="현재 재생 중인 음악의 정보를 표시합니다.")
    async def Now_Playing(self, ctx):
        Print_Log("Music", "곡 정보 확인 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name)
        
        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.is_playing():
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)
        else:
            Song = Player.current["info"]
            embed = await self.Build_Embed(song, ctx, f"**{song['title']}** 음악을 재생하고 있습니다.")
            await ctx.respond(embed=embed)

    # /음악 볼륨 [크기]
    @Music_CMDGroup.command(name="볼륨", description="음악 볼륨을 조절합니다.")
    async def Volume(self, ctx, Value: discord.Option(int, name="크기", description="볼륨 크기 (0 ~ 500)", required=True)):
        Print_Log("Music", "볼륨 조절 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name, extra=f"설정 값: {Value}%")
        
        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Voice:
            return await ctx.respond(embed=Error_Dialog_Embed("재생 중인 음악이 없습니다."), ephemeral=True)

        if Value < 0 or Value > 500:
            return await ctx.respond(embed=Error_Dialog_Embed("볼륨은 0 이상 500 이하의 정수여야 합니다."), ephemeral=True)

        # 볼륨 조절
        Player.Set_Volume(Value / 100)
        await ctx.respond(embed=Success_Dialog_Embed(f"애플리케이션의 볼륨을 **{Value}%** 로 설정했습니다."))

    # 대기열 명령어 그룹
    Queue_CMDGroup = Music_CMDGroup.create_subgroup("대기열", "대기열 관련 명령어입니다.")

    # /대기열 목록
    @Queue_CMDGroup.command(name="목록", description="대기열을 표시합니다.")
    async def Queue_List(self, ctx):
        Print_Log("Music", "대기열 목록 확인 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name)
        
        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Queue:
            return await ctx.respond(embed=Error_Dialog_Embed("대기열에 음악이 존재하지 않습니다."), ephemeral=True)

        # 임베드 및 뷰 생성
        embed, _ = self.Queue_Page(ctx, Player, 1)
        View = QueueView(ctx, Player, self.Queue_Page)

        await ctx.respond(embed=embed, view=View)

    # /대기열 초기화
    @Queue_CMDGroup.command(name="초기화", description="대기열을 초기화합니다.")
    async def Queue_Clear(self, ctx):
        Print_Log("Music", "대기열 초기화 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name)
        
        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Queue:
            return await ctx.respond(embed=Error_Dialog_Embed("대기열에 음악이 존재하지 않습니다."), ephemeral=True)

        # 삭제된 곡 수 계산
        Cleared_Count = len(Player.Queue)
        Player.Queue.clear()
        await ctx.respond(embed=Success_Dialog_Embed(f"대기열을 초기화했습니다. (삭제된 곡 수: {Cleared_Count}개)"))

    # /대기열 삭제 [번호]
    @Queue_CMDGroup.command(name="삭제", description="대기열에서 음악을 삭제합니다.")
    async def Queue_Delete(self, ctx, position: discord.Option(int, name="번호", description="삭제할 음악의 번호", required=True)):
        Print_Log("Music", "대기열 곡 삭제 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name, extra=f"위치: {position}")
        
        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Queue:
            return await ctx.respond(embed=Error_Dialog_Embed("대기열에 음악이 존재하지 않습니다."), ephemeral=True)

        if position < 1 or position > len(Player.Queue):
            return await ctx.respond(embed=Error_Dialog_Embed(f"올바른 번호를 입력하세요. (1 ~ {len(Player.Queue)})"), ephemeral=True)

        # 대기열에서 곡 삭제
        Removed = Player.Queue.pop(position - 1)
        Title = Removed["info"]["title"]

        await ctx.respond(embed=Success_Dialog_Embed(f"**{Title}** 음악을 대기열에서 삭제했습니다."))

    # /대기열 재생 [번호]
    @Queue_CMDGroup.command(name="재생", description="대기열에서 원하는 번호의 곡을 바로 재생합니다.")
    async def Queue_Play(self, ctx, num: discord.Option(int, name="번호", description="재생할 곡의 번호", required=True)):
        Print_Log("Music", "대기열 특정 곡 재생 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name, extra=f"번호: {num}")
        
        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Queue:
            return await ctx.respond(embed=Error_Dialog_Embed("대기열에 음악이 존재하지 않습니다."), ephemeral=True)

        if num < 1 or num > len(Player.Queue):
            return await ctx.respond(embed=Error_Dialog_Embed(f"올바른 번호를 입력하세요. (1 ~ {len(Player.Queue)})"), ephemeral=True)
        
        voice = ctx.voice_client
        if not voice or not voice.channel:
            return

        Members = [m for m in voice.channel.members if not m.bot]
        Queue_Item = Player.Queue[num - 1]
        Title = Queue_Item["info"]["title"]

        # 사용자가 1명이거나 관리자이면 즉시 곡 재생
        if len(Members) <= 1 or ctx.author.guild_permissions.administrator:
            Success = await Player.Play_From_Queue(num)

            if not Success:
                return await ctx.respond(embed=Error_Dialog_Embed("음악을 재생하지 못했습니다."), ephemeral=True)
            
            Player.Suppress_Next_Start_embed = True
            return await ctx.respond(embed=Success_Dialog_Embed(f"**{Title}** 음악을 재생합니다."))

        # 필요한 투표 수 계산
        Required_Votes = (len(Members) // 2) + 1

        # 곡 재생 투표 진행
        embed = discord.Embed(
            title=f":white_check_mark: **{Title}** 음악을 재생할까요?",
            description=(
                f"음성 채널에 사용자가 2명 이상이므로 투표를 진행합니다.\n\n"
                f"필요 찬성 수: **{Required_Votes}**\n"
                f"투표 시간: **30초**"))
        
        async def action():
            Player.Suppress_Next_Start_embed = True
            await Player.Play_From_Queue(num)

        View = VoteView(ctx, Player, Required_Votes, action=action, success_message=f":white_check_mark: 투표가 통과되어 **{Title}** 음악을 재생합니다.")
        await ctx.respond(embed=embed, view=View)

    # 대기열 셔플 명령어
    @Queue_CMDGroup.command(name="셔플", description="대기열을 셔플합니다.")
    async def Shuffle(self, ctx):
        Print_Log("Music", "대기열 셔플 명령어를 사용했습니다.", ctx.guild.name, ctx.author.name)
        
        # 길드 별 플레이어 지정
        Player = self.Players.get(ctx.guild.id)

        if not Player or not Player.Queue:
            return await ctx.respond(embed=Error_Dialog_Embed("대기열에 음악이 존재하지 않습니다."), ephemeral=True)

        Success = await Player.Shuffle_Queue()

        if not Success:
            return await ctx.respond(embed=Error_Dialog_Embed("대기열에 2개 이상의 곡을 추가해 주세요."), ephemeral=True)

        await ctx.respond(embed=Success_Dialog_Embed("대기열을 셔플했습니다."))

def setup(bot):
    bot.add_cog(Music(bot))