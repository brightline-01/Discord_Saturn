import discord
import datetime
import re
import asyncio
import random
from discord.ext import commands
from pytubefix import YouTube, Search, Playlist

# URL 체크 스크립트
def Check_YT_URL(text: str) -> bool:
    return re.match(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/", text) is not None

# 재생 목록 URL 체크 스크립트
def Check_Playlist_URL(url: str) -> bool:
    return "list=" in url

# MusicPlayer 클래스
class MusicPlayer:
    def __init__(self, bot, FFMPEG_OPTIONS: dict):
        self.bot = bot
        self.FFMPEG_OPTIONS = FFMPEG_OPTIONS    # FFMPEG 옵션
        self.voice: discord.VoiceClient | None = None   # Voice Client
        self.queue: list[dict] = []     # 대기열
        self.history: list[dict] = []   # 이전 곡
        self.current: dict | None = None    # 현재 곡
        self._lock = asyncio.Lock()     # Asyncio Lock
        self.loop = False   # 단일 반복 (기본 False)
        self.loop_queue = False     # 대기열 반복 (기본 False)
        self.on_song_start = None   # 곡 재생 시
        self.suppress_next_start_embed = False  # Embed 출력 여부
        self.volume = 1.0   # 볼륨 (기본 1.0)
        self._manual_stop = False   # 이전 곡으로 인한 정지
    
    # 곡 재생 상태 체크 스크립트
    def is_playing(self) -> bool:
        return self.voice is not None and self.voice.is_playing()

    # 일시 정지 상태 체크 스크립트
    def is_paused(self) -> bool:
        return self.voice is not None and self.voice.is_paused()

    # 곡 재생 스크립트
    async def play(self, stream_url: str, song_info: dict):
        async with self._lock:
            try:
                source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(stream_url, **self.FFMPEG_OPTIONS), volume=self.volume)
                self.current = {"url": stream_url, "info": song_info}
                if self.on_song_start and not self.suppress_next_start_embed and not self.loop and not self.loop_queue:
                    await self.on_song_start(song_info)
                self.suppress_next_start_embed = False
                self.voice.play(source, after=lambda e: self.bot.loop.create_task(self._after_play(e)))
            except Exception as e:
                print(f"[Music | MusicPlayer] 재생 오류: {e}")

    # 곡 정지 시 스크립트
    async def _after_play(self, error):
        if error:
            print(f"[MusicPlayer] FFmpeg 오류: {error}")

        if self._manual_stop:
            self._manual_stop = False
            return

        if self.loop and self.current:
            return await self.play(self.current["url"], self.current["info"])

        if self.current:
            self.history.append(self.current)
            
            if self.loop_queue:
                self.queue.append(self.current)

        await self.play_next()

    # 다음 곡 재생 스크립트
    async def play_next(self):
        if not self.queue:
            self.current = None

            if self.voice and self.voice.is_connected():
                await self.voice.disconnect()
                self.voice = None

            return

        next_song = self.queue.pop(0)
        await self.play(next_song["url"], next_song["info"])

    # 대기열에 곡 추가 스크립트
    def Add_to_Queue(self, stream_url: str, song_info: dict):
        self.queue.append({"url": stream_url, "info": song_info})

    # 이전 곡 재생 스크립트
    async def play_previous(self):
        if not self.history:
            return False

        prev = self.history.pop()
        prev_loop = self.loop
        prev_loop_queue = self.loop_queue
        self.loop = False
        self.loop_queue = False
        self._manual_stop = True

        self.queue.insert(0, self.current)
            
        if self.voice and self.voice.is_playing():
            self.voice.stop()
        
        await self.play(prev["url"], prev["info"])

        self.loop = prev_loop
        self.loop_queue = prev_loop_queue

        return True

    # 곡 일시 정지 스크립트
    def pause(self):
        if self.is_playing():
            self.voice.pause()

    # 곡 재개 스크립트
    def resume(self):
        if self.is_paused():
            self.voice.resume()

    # 스킵 스크립트
    def skip(self):
        if self.voice and self.is_playing():
            self.voice.stop()

    # 곡 정지 스크립트
    async def stop(self):
        self.queue.clear()
        self.history.clear()
        self.current = None

        if not self.voice or not self.voice.is_connected():
            return

        if self.voice:
            self.voice.stop()
            await self.voice.disconnect()
            self.voice = None

    # 볼륨 조절 스크립트 (최소 0% ~ 최대 500%)
    def Set_VOL(self, volume: float):
        self.volume = max(0.0, min(volume, 5.0))

        if self.voice and self.voice.source:
            self.voice.source.volume = self.volume

    # 대기열에서 재생 스크립트
    async def play_from_Queue(self, position: int):
        if position < 1 or position > len(self.queue):
            return False

        if self.current:
            self.history.append(self.current)
        
        if self.loop_queue and self.current:
            self.queue.append(self.current)

        song = self.queue.pop(position - 1)
        self._manual_stop = True

        if self.voice and self.is_playing():
            self.voice.stop()

        await self.play(song["url"], song["info"])
        
        if self.loop_queue and self.current:
            self.queue.append(self.current)

        return True
    
    # 대기열 셔플 스크립트
    async def shuffle_Queue(self):
        if not self.queue or len(self.queue) < 2:
            return False

        random.shuffle(self.queue)
        return True

# QueueView 클래스
class QueueView(discord.ui.View):
    def __init__(self, ctx, player, queue_page_func):
        super().__init__(timeout=120)
        self.ctx = ctx  # ctx
        self.player = player    # 플레이어
        self.queue_page = queue_page_func   # 대기열 페이지
        self.page = 1   # 페이지
        self.update_buttons()   # 버튼 업데이트 실행

    # 버튼 업데이트 스크립트
    def update_buttons(self):
        self.clear_items()

        total_pages = max(1, (len(self.player.queue) + 9) // 10)

        self.add_item(self.Button("⏪", self.page > 1, self.first))
        self.add_item(self.Button("⬅️", self.page > 1, self.prev))
        self.add_item(self.Button("➡️", self.page < total_pages, self.next))
        self.add_item(self.Button("⏩", self.page < total_pages, self.last))

    # 대기열 메세지 업데이트 스크립트
    async def update(self, interaction):
        embed, total = self.queue_page(self.ctx, self.player, self.page)
        self.update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    # Button 클래스
    class Button(discord.ui.Button):
        def __init__(self, emoji, enabled, callback):
            super().__init__(style=discord.ButtonStyle.secondary, emoji=emoji, disabled=not enabled)
            self.cb = callback

        async def callback(self, interaction):
            await self.cb(interaction)

    # 처음으로 버튼
    async def first(self, interaction):
        self.page = 1
        await self.update(interaction)

    # 이전으로 버튼
    async def prev(self, interaction):
        self.page -= 1
        await self.update(interaction)

    # 다음으로 버튼
    async def next(self, interaction):
        self.page += 1
        await self.update(interaction)

    # 맨 뒤로 버튼
    async def last(self, interaction):
        self.page = (len(self.player.queue) + 9) // 10
        await self.update(interaction)

# VoteView 클래스
class VoteView(discord.ui.View):
    def __init__(self, ctx, player, required_votes, action, success_message = str):
        super().__init__(timeout=30)
        self.ctx = ctx  # ctx
        self.player = player    # 플레이어
        self.required_votes = required_votes    # 필요한 투표 수
        self.votes = set()  # 투표 수
        self.action = action
        self.success_message = success_message

    # 투표 스크립트
    @discord.ui.button(label="투표하기", style=discord.ButtonStyle.danger)
    async def vote(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.bot:
            return
        if interaction.user not in self.ctx.author.voice.channel.members:
            return await interaction.response.send_message(embed=discord.Embed(description=":warning: 음성 채널에 있는 사용자만 투표할 수 있습니다."), ephemeral=True)

        if interaction.user.id in self.votes:
            return await interaction.response.send_message(embed=discord.Embed(description=":warning: 이미 투표하셨습니다."), ephemeral=True)

        self.votes.add(interaction.user.id)

        if len(self.votes) >= self.required_votes:
            await self.action()
            self.stop()
            return await interaction.response.edit_message(embed=discord.Embed(description=self.success_message), view=None)

        await interaction.response.edit_message(embed=discord.Embed(description=f"투표가 진행 중입니다.\n"f"찬성: **{len(self.votes)} / {self.required_votes}**"), view=self)

# PlaylistConfirmView 클래스
class PlaylistConfirmView(discord.ui.View):
    def __init__(self, author, playlist_url, player):
        super().__init__(timeout=30)
        self.author = author    # 명령어 사용자
        self.playlist_url = playlist_url    # 재생목록 URL
        self.player = player    # 플레이어
        self.value = None   # 값

    # 인터랙션 사용자 체크 스크립트
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message(":warning: 이 버튼은 명령어를 실행한 사용자만 사용할 수 있습니다.", ephemeral=True)
            return False
        return True

    # 재생 목록 곡 추가 반환
    @discord.ui.button(label="추가하기", style=discord.ButtonStyle.green)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        await interaction.response.defer()
        self.stop()

    # 재생목록 곡 추가 취소 반환
    @discord.ui.button(label="취소", style=discord.ButtonStyle.red)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        await interaction.response.defer()
        self.stop()

    # 시간 초과 스크립트
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

# Music_Commands 클래스
class Music_Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.FFMPEG_OPTIONS = {     # FFMPEG 옵션
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
            }
        self.PYTUBEFIX_OPTIONS = {'only_audio': True, 'abr': '160kbps'}     # PYTUBEFIX 옵션
        self.players = {}   # 길드 별 플레이어

    # 애플리케이션 자동 퇴장 스크립트
    @discord.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        guild = member.guild
        player = self.players.get(guild.id)

        if not player or not player.voice:
            return

        voice = player.voice
        channel = voice.channel

        if not channel:
            return

        peoples = [m for m in channel.members if not m.bot]

        if len(peoples) == 0:
            await player.stop()

    # 곡 정보 빌드 스크립트
    def Build_Song_Info(self, yt, ctx, queue_position=0):
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

    # 곡 길이 포맷 스크립트
    def Format_Duration(self, seconds: int) -> str:
        if seconds is None:
            return "알 수 없음"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
    
    # 곡 Embed 빌드 스크립트
    async def Build_Embed(self, song_info, ctx, description):
        embed = discord.Embed(
            title=(f":musical_note: {song_info['title']}"),
            description=description,
            url=song_info.get('webpage_url'),
            color=discord.Color.blue()
        )
        embed.add_field(name="영상 길이", value=self.Format_Duration(song_info['duration']), inline=True)
        embed.add_field(name="채널", value=song_info['uploader'], inline=True)
        embed.set_thumbnail(url=song_info['thumbnail'])
        embed.set_footer(text=f"요청자 : {song_info['requester']}")
        return embed
    
    # 곡 Embed 전송 스크립트
    async def Send_embed_on_song_start(self, song_info):
        channel = song_info.get("text_channel")
        if not channel:
            return

        embed = await self.Build_Embed(song_info, None, f"**{song_info['title']}** 음악을 재생하고 있습니다.")
        await channel.send(embed=embed)

    # 대기열 페이지 표시 스크립트
    def Queue_Page(self, ctx, player: MusicPlayer, page_num: int, songs_per_page=10):
        queue = player.queue
        start_index = (page_num - 1) * songs_per_page
        end_index = min(start_index + songs_per_page, len(queue))

        if start_index >= len(queue):
            return None, None

        embed = discord.Embed(title=":notes: 대기열을 표시합니다.", description="현재 대기열 목록:", color=discord.Color.blue())

        if player.current:
            info = player.current["info"]
            embed.add_field(name=f"현재 재생 중: {info['title']}", value=f"길이: {self.Format_Duration(info['duration'])} | 요청자: {info['requester']}",inline=False)

        for i in range(start_index, end_index):
            info = queue[i]["info"]
            embed.add_field(name=f"{i + 1}. {info['title']}", value=f"길이: {self.Format_Duration(info['duration'])} | 요청자: {info['requester']}", inline=False)

        total_pages = (len(queue) + songs_per_page - 1) // songs_per_page
        embed.set_footer(text=f"페이지 {page_num} / {total_pages}")

        return embed, total_pages

    # 재생 목록 곡 추가 스크립트
    async def Add_Playlist_to_Queue(self, url, ctx, player):
        playlist = Playlist(url)
        videos = list(playlist.videos)

        added = 0
        rest_videos = videos[1:]

        for yt in rest_videos:
            stream = yt.streams.filter(**self.PYTUBEFIX_OPTIONS).order_by("abr").desc().first()

            if stream is None:
                continue

            info = self.Build_Song_Info(yt, ctx, queue_position=len(player.queue) + 1)

            player.Add_to_Queue(stream.url, info)
            added += 1

        await ctx.respond(embed=discord.Embed(description=f":white_check_mark: 재생목록에서 **{added}곡**을 대기열에 추가했습니다."))

    # 음성 채널 입장 스크립트
    async def Ensure_VC(self, ctx, player):
        if not ctx.author.voice:
            await ctx.respond(embed=discord.Embed(description=":warning: 먼저 음성 채널에 연결해주세요."), ephemeral=True)
            return False

        channel = ctx.author.voice.channel

        if ctx.voice_client and ctx.voice_client.channel != channel:
            await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션이 같은 서버의 다른 음성 채널에서 재생 중입니다. 애플리케이션의 연결을 끊거나 기다린 후 다시 시도하세요."), ephemeral=True)
            return False

        if not ctx.voice_client:
            player.voice = await channel.connect()
        else:
            player.voice = ctx.voice_client

        return True

    Music = discord.SlashCommandGroup("음악")   # 음악 슬래쉬 커맨드 그룹

    # 재생 명령어
    @Music.command(name="재생", description="YouTube에서 음악을 찾아 재생합니다.", options=[discord.Option(str, name="제목", description="재생할 음악의 제목 또는 URL", required=True)])
    async def play(self, ctx, *, url: str):
        print(f"[Music | Command Event] 재생 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        await ctx.defer()

        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player:
            player = MusicPlayer(self.bot, self.FFMPEG_OPTIONS)
            self.players[ctx.guild.id] = player

        player.on_song_start = self.Send_embed_on_song_start

        # 음성 채널 입장
        if not await self.Ensure_VC(ctx, player):
            return

        # 재생 목록 URL 체크
        if Check_Playlist_URL(url):
            playlist = Playlist(url)
            videos = list(playlist.videos)
            view = PlaylistConfirmView(ctx.author, url, player)

            first_video = videos[0]
            first_stream = first_video.streams.filter(**self.PYTUBEFIX_OPTIONS).order_by("abr").desc().first()
            first_info = self.Build_Song_Info(first_video, ctx, queue_position=len(player.queue) + 1)

            if player.is_playing():
                player.Add_to_Queue(first_stream.url, first_info)
            else:
                player.suppress_next_start_embed = True
                await player.play(first_stream.url, first_info)
                embed = await self.Build_Embed(first_info, ctx, description=f"**{first_info['title']}** 음악을 재생하고 있습니다.")
                await ctx.respond(embed=embed)

            embed = discord.Embed(title="📃 재생목록 링크를 감지했습니다.", description="이 재생목록의 모든 곡을 대기열에 추가할까요?")
            msg = await ctx.followup.send(embed=embed, view=view)
            await view.wait()

            for item in view.children:
                item.disabled = True
            await msg.edit(view=view)

            if view.value is None:
                return await ctx.followup.send(embed=discord.Embed(description=":warning: 시간이 초과되어 동작을 실행하지 않습니다."), ephemeral=True)

            if not view.value:
                return await ctx.followup.send(embed=discord.Embed(description=":white_check_mark: 재생목록의 곡을 추가하지 않았습니다."), ephemeral=True)

            return await self.Add_Playlist_to_Queue(url, ctx, player)

        # URL 체크
        if Check_YT_URL(url):
            yt = YouTube(url)
        else:
            search = Search(url)
            if not search.results:return await ctx.respond(embed=discord.Embed(description=":warning: 검색 결과를 찾을 수 없습니다."), ephemeral=True)
            yt = search.results[0]

        # 곡 정보 저장
        stream = yt.streams.filter(**self.PYTUBEFIX_OPTIONS).order_by("abr").desc().first()
        song_info = self.Build_Song_Info(yt, ctx, queue_position=len(player.queue) + 1)

        # 곡 재생
        if player.is_playing():
            player.Add_to_Queue(stream.url, song_info)
            embed = await self.Build_Embed(song_info, ctx, description=f"**{yt.title}** 음악을 대기열에 추가했습니다.")
            print(f"[Music | Command Event] 대기열에 곡 추가 완료 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
            return await ctx.respond(embed=embed)
        else:
            player.suppress_next_start_embed = True
            await player.play(stream.url, song_info)
            embed = await self.Build_Embed(song_info, ctx, description=f"**{yt.title}** 음악을 재생하고 있습니다.")
            return await ctx.respond(embed=embed)

    # 검색 명령어
    @Music.command(name="검색", description="YouTube에서 음악을 지정한 개수만큼 검색합니다.", options=[
        discord.Option(str, name="제목", description="검색할 음악의 제목", required=True),
        discord.Option(int, name="개수", description="검색할 개수 (1 ~ 10, 기본값: 5, 선택)", required=False, min_value=1, max_value=10, default=5)])
    async def search(self, ctx, *, query: str, index: int):
        print(f"[Music | Command Event] 검색 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        await ctx.defer()
        
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정
        
        if not player:
            player = MusicPlayer(self.bot, self.FFMPEG_OPTIONS)
            self.players[ctx.guild.id] = player

        player.on_song_start = self.Send_embed_on_song_start

        # 음성 채널 입장
        if not await self.Ensure_VC(ctx, player):
            return
        
        # 검색
        search = Search(query)
        results = search.results[:index]

        if not search.results:
            return await ctx.respond(embed=discord.Embed(description=":warning: 검색 결과가 없습니다."), ephemeral=True)

        # 검색 결과 표시
        embed = discord.Embed(title=f":notes: '{query}'에 대한 검색 결과", color=discord.Color.blue())

        for i, yt in enumerate(results, start=1):
            duration = self.Format_Duration(yt.length) if yt.length else "알 수 없음"
            embed.add_field(name=f"{i}. {yt.title}", value=f"채널: {yt.author}\n길이: {duration}", inline=False)

        await ctx.respond(content=":white_check_mark: 30초 내에 번호를 입력하여 해당 음악을 재생할 수 있습니다.", embed=embed)

        def check(m):
            return (m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= len(results))

        # 곡 재생
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=30)
            index = int(msg.content) - 1
            yt = results[index]
            stream = yt.streams.filter(**self.PYTUBEFIX_OPTIONS).order_by("abr").desc().first()
            song_info = self.Build_Song_Info(yt, ctx, queue_position=len(player.queue) + 1)

            if player.is_playing():
                player.Add_to_Queue(stream.url, song_info)
                embed = await self.Build_Embed(song_info, ctx, description=f"**{yt.title}** 음악을 대기열에 추가했습니다.")
                return await ctx.respond(embed=embed)
            else:
                player.suppress_next_start_embed = True
                await player.play(stream.url, song_info)
                embed = await self.Build_Embed(song_info, ctx, description=f"**{yt.title}** 음악을 재생하고 있습니다.")
                return await ctx.respond(embed=embed)

        # 시간 초과 시 스크립트
        except asyncio.TimeoutError:
            await ctx.send(embed=discord.Embed(description=":warning: 시간이 초과되어 동작을 실행하지 않습니다."))

    # 스킵 명령어
    @Music.command(name="스킵", description="현재 재생 중인 곡을 건너 뜁니다.")
    async def skip(self, ctx):
        print(f"[Music | Command Event] 스킵 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.is_playing():
            return await ctx.respond(embed=discord.Embed(description=":warning: 재생 중인 음악이 없습니다."), ephemeral=True)

        if not player.queue and not player.loop:
            return await ctx.respond(embed=discord.Embed(description=":warning: 다음 곡을 찾을 수 없습니다."), ephemeral=True)

        voice = ctx.voice_client
        if not voice or not voice.channel:
            return

        members = [m for m in voice.channel.members if not m.bot]   # 음성 채널 사용자 수 감지 (애플리케이션 제외)

        # 사용자가 1명이거나 관리자이면 즉시 스킵
        if len(members) <= 1 or ctx.author.guild_permissions.administrator:
            player.skip()
            return await ctx.respond(embed=discord.Embed(description=":white_check_mark: 재생 중인 음악을 건너뛰었습니다."))

        required_votes = (len(members) // 2) + 1    # 필요한 투표 수 계산

        # 스킵 투표 진행
        embed = discord.Embed(
            title=":white_check_mark: 이 음악을 건너 뛸까요?",
            description=(
                f"음성 채널에 사용자가 2명 이상이므로 투표를 진행합니다.\n\n"
                f"필요 찬성 수: **{required_votes}**\n"
                f"투표 시간: **30초**"))
        view = VoteView(ctx, player, required_votes, action=player.skip, success_message=":white_check_mark: 투표가 통과되어 재생 중인 음악을 건너뛰었습니다.")
        await ctx.respond(embed=embed, view=view)

    # 곡 정지 명령어
    @Music.command(name="정지", description="재생 중인 음악을 정지하고 대기열을 초기화합니다.")
    async def stop(self, ctx):
        print(f"[Music | Command Event] 곡 정지 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.voice:
            return await ctx.respond(embed=discord.Embed(description=":warning: 재생 중인 음악이 없습니다."), ephemeral=True)
        
        await player.stop()
        self.players.pop(ctx.guild.id, None)

        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 재생 중인 음악을 정지하고 대기열을 초기화했습니다."))

    # 곡 일시 정지 명령어
    @Music.command(name="일시정지", description="재생 중인 음악을 일시정지합니다.")
    async def pause(self, ctx):
        print(f"[Music | Command Event] 곡 일시 정지 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.is_playing():
            return await ctx.respond(embed=discord.Embed(description=":warning: 재생 중인 음악이 없습니다."), ephemeral=True)

        player.pause()

        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 재생 중인 음악을 일시정지했습니다."))
        
    # 곡 재개 명령어
    @Music.command(name="재개", description="일시 정지한 음악을 다시 재생합니다.")
    async def resume(self, ctx):
        print(f"[Music | Command Event] 곡 재개 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.is_paused():
            return await ctx.respond(embed=discord.Embed(description=":warning: 재생 중인 음악이 없습니다."), ephemeral=True)

        player.resume()

        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 일시 정지한 음악을 다시 재생했습니다."))

    # 곡 반복 명령어
    @Music.command(name="반복", description="현재 음악을 반복할 옵션을 선택합니다.", options=[discord.Option(str, name="모드", description="반복 모드", choices=["대기열", "단일", "끄기"], required=True)])
    async def loop(self, ctx, mode: str):
        print(f"[Music | Command Event] 곡 반복 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.is_playing():
            return await ctx.respond(embed=discord.Embed(description=":warning: 재생 중인 음악이 없습니다."), ephemeral=True)

        # 모드가 대기열 반복이라면
        if mode == "대기열":
            player.loop_queue = True
            player.loop = False

            await ctx.respond(embed=discord.Embed(description=":white_check_mark: 반복 모드를 **대기열 반복**으로 설정했습니다."))

        # 모드가 단일 반복이라면
        elif mode == "단일":
            player.loop = True
            player.loop_queue = False

            await ctx.respond(embed=discord.Embed(description=":white_check_mark: 반복 모드를 **단일 반복**으로 설정했습니다."))

        # 모드가 끄기라면
        elif mode == "끄기":
            player.loop = False
            player.loop_queue = False

            await ctx.respond(embed=discord.Embed(description=":white_check_mark: 반복 모드를 **해제**했습니다."))

    # 이전 곡 재생 명령어
    @Music.command(name="이전곡", description="이전 곡을 다시 재생합니다.")
    async def previous(self, ctx):
        print(f"[Music | Command Event] 이전 곡 재생 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.current:
            return await ctx.respond(embed=discord.Embed(description=":warning: 재생 중인 음악이 없습니다."), ephemeral=True)

        if not player.history:
            return await ctx.respond(embed=discord.Embed(description=":warning: 이전 곡을 찾을 수 없습니다."), ephemeral=True)
        
        prev_info = player.history[-1]["info"]
        prev_title = prev_info["title"]

        voice = ctx.voice_client
        if not voice or not voice.channel:
            return

        members = [m for m in voice.channel.members if not m.bot]   # 음성 채널 사용자 수 감지 (애플리케이션 제외)

        # 사용자가 1명이거나 관리자이면 즉시 이전 곡 재생
        if len(members) <= 1 or ctx.author.guild_permissions.administrator:
            player.suppress_next_start_embed = True
            await player.play_previous()
            return await ctx.respond(embed=discord.Embed(description=f":white_check_mark: **{prev_title}** 음악을 재생합니다."))

        required_votes = (len(members) // 2) + 1    # 필요한 투표 수 계산

        # 이전 곡 재생 투표 진행
        embed = discord.Embed(
            title=":white_check_mark: 이전 곡을 재생할까요?",
            description=(
                f"음성 채널에 사용자가 2명 이상이므로 투표를 진행합니다.\n\n"
                f"필요 찬성 수: **{required_votes}**\n"
                f"투표 시간: **30초**"))
        
        async def action():
            player.suppress_next_start_embed = True
            player.play_previous
        view = VoteView(ctx, player, required_votes, action=action, success_message=f":white_check_mark: 투표가 통과되어 **{prev_title}** 음악을 재생합니다.")
        await ctx.respond(embed=embed, view=view)

    # 곡 정보 명령어
    @Music.command(name="정보", description="현재 재생 중인 음악의 정보를 표시합니다.")
    async def now(self, ctx):
        print(f"[Music | Command Event] 곡 정보 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.is_playing():
            return await ctx.respond(embed=discord.Embed(description=":warning: 재생 중인 음악이 없습니다."), ephemeral=True)
        else:
            song = player.current["info"]
            embed = await self.Build_Embed(song, ctx, f"**{song['title']}** 음악을 재생하고 있습니다.")
            await ctx.respond(embed=embed)

    # 볼륨 조절 명령어
    @Music.command(name="볼륨", description="음악 볼륨을 조절합니다.", options=[discord.Option(int, name="크기", description="볼륨 크기 (0 ~ 500)", required=True)])
    async def volume(self, ctx, value: int):
        print(f"[Music | Command Event] 볼륨 조절 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.voice:
            return await ctx.respond(embed=discord.Embed(description=":warning: 재생 중인 음악이 없습니다."), ephemeral=True)

        if value < 0 or value > 500:
            return await ctx.respond(embed=discord.Embed(description=":warning: 볼륨은 0 이상 500 이하의 정수여야 합니다."), ephemeral=True)

        player.Set_VOL(value / 100)     # 볼륨 조절
        await ctx.respond(embed=discord.Embed(description=f":white_check_mark: 애플리케이션의 볼륨을 **{value}%** 로 설정했습니다."))

    Queue = Music.create_subgroup("대기열", "대기열 관련 명령어입니다.")    # 대기열 슬래쉬 커맨드 그룹

    # 대기열 표시 명령어
    @Queue.command(name="목록", description="대기열을 표시합니다.")
    async def queue(self, ctx):
        print(f"[Music | Command Event] 대기열 표시 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.queue:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열에 음악이 존재하지 않습니다."), ephemeral=True)

        embed, _ = self.Queue_Page(ctx, player, 1)
        view = QueueView(ctx, player, self.Queue_Page)

        await ctx.respond(embed=embed, view=view)

    # 대기열 초기화 명령어
    @Queue.command(name="초기화", description="대기열을 초기화합니다.")
    async def queue_clear(self, ctx):
        print(f"[Music | Command Event] 대기열 초기화 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.queue:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열에 음악이 존재하지 않습니다."), ephemeral=True)

        cleared_count = len(player.queue)   # 삭제된 곡 수
        player.queue.clear()

        await ctx.respond(embed=discord.Embed(description=f":white_check_mark: 대기열을 초기화했습니다. (삭제된 곡 수: {cleared_count}개)"))

    # 대기열 곡 삭제 명령어
    @Queue.command(name="삭제", description="대기열에서 음악을 삭제합니다.", options=[discord.Option(int, name="num", description="삭제할 음악의 num", required=True)])
    async def queue_delete(self, ctx, position: int):
        print(f"[Music | Command Event] 대기열 곡 삭제 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.queue:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열에 음악이 존재하지 않습니다."), ephemeral=True)

        if position < 1 or position > len(player.queue):
            return await ctx.respond(embed=discord.Embed(description=f":warning: 올바른 번호를 입력하세요. (1 ~ {len(player.queue)})"), ephemeral=True)

        removed = player.queue.pop(position - 1)
        title = removed["info"]["title"]

        await ctx.respond(embed=discord.Embed(description=f":white_check_mark: **{title}** 음악을 대기열에서 삭제했습니다."))

    # 대기열에서 곡 재생 명령어
    @Queue.command(name="재생", description="대기열에서 원하는 번호의 곡을 바로 재생합니다.", options=[discord.Option(int, name="번호", description="재생할 곡의 번호", required=True)])
    async def queue_play(self, ctx, num: int):
        print(f"[Music | Command Event] 대기열에서 곡 재생 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.queue:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열에 음악이 존재하지 않습니다."), ephemeral=True)

        if num < 1 or num > len(player.queue):
            return await ctx.respond(embed=discord.Embed(description=f":warning: 올바른 번호를 입력하세요. (1 ~ {len(player.queue)})"), ephemeral=True)

        
        voice = ctx.voice_client
        if not voice or not voice.channel:
            return

        members = [m for m in voice.channel.members if not m.bot]   # 음성 채널 사용자 수 감지 (애플리케이션 제외)
        queue_item = player.queue[num - 1]
        title = queue_item["info"]["title"]    # 곡 이름 불러오기

        # 사용자가 1명이거나 관리자이면 즉시 곡 재생
        if len(members) <= 1 or ctx.author.guild_permissions.administrator:
            success = await player.play_from_Queue(num)

            if not success:
                return await ctx.respond(embed=discord.Embed(description=":warning: 음악을 재생하지 못했습니다."), ephemeral=True)
            
            player.suppress_next_start_embed = True
            return await ctx.respond(embed=discord.Embed(description=f":white_check_mark: **{title}** 음악을 재생합니다."))

        required_votes = (len(members) // 2) + 1    # 필요한 투표 수 계산

        # 곡 재생 투표 진행
        embed = discord.Embed(
            title=f":white_check_mark: **{title}** 음악을 재생할까요?",
            description=(
                f"음성 채널에 사용자가 2명 이상이므로 투표를 진행합니다.\n\n"
                f"필요 찬성 수: **{required_votes}**\n"
                f"투표 시간: **30초**"))
        
        async def action():
            player.suppress_next_start_embed = True
            await player.play_from_Queue(num)

        view = VoteView(ctx, player, required_votes, action=action, success_message=f":white_check_mark: 투표가 통과되어 **{title}** 음악을 재생합니다.")
        await ctx.respond(embed=embed, view=view)

    # 대기열 셔플 명령어
    @Queue.command(name="셔플", description="대기열을 셔플합니다.")
    async def shuffle(self, ctx):
        print(f"[Music | Command Event] 대기열 셔플 명령어 사용 (서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        player = self.players.get(ctx.guild.id)     # 길드 별 플레이어 지정

        if not player or not player.queue:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열에 음악이 존재하지 않습니다."), ephemeral=True)

        success = await player.shuffle_Queue()

        if not success:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열에 2개 이상의 곡을 추가해 주세요."), ephemeral=True)

        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 대기열을 셔플했습니다."))

def setup(bot):
    bot.add_cog(Music_Commands(bot))