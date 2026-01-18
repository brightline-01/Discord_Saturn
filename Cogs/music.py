import discord
import asyncio
import yt_dlp
import datetime
import random
from discord.ext import commands
from discord.ui import View, Button
from discord import ButtonStyle

class SkipVoteView(View):
    def __init__(self):
        super().__init__(timeout=30)
        self.votes = 0
        self.users_voted = set()

    @discord.ui.button(label="건너뛰기", style=discord.ButtonStyle.green, emoji="✅")
    async def vote_skip(self, button: Button, interaction: discord.Interaction):
        user = interaction.user
        if user.id in self.users_voted:
            await interaction.response.send_message(embed=discord.Embed(description=":warning: 이미 투표에 참여했습니다."), ephemeral=True)
        else:
            self.votes += 1
            self.users_voted.add(user.id)
            await interaction.response.send_message(embed=discord.Embed(description=":white_check_mark: 투표를 등록했습니다."), ephemeral=True)

    def get_votes(self):
        return self.votes
    
class music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.YDL_OPT = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'noplaylist': True,
            'bypass_geo_restriction': True,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'cachedir': False,
            'extractaudio': True
        }
        self.FFMPEG_OPT = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }
        self.loop = {}
        self.queue_loop = {}
        self.current_volume = {}
        self.current_song = {}
        self.previous_song = {}
        self.queue = []

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        voice = self.bot.voice_clients[0] if self.bot.voice_clients else None

        if before.channel is not None and after.channel is None:
            if len(before.channel.members) == 1 and voice and voice.channel == before.channel:
                if voice.is_playing():
                    voice.stop()
                    self.queue.clear()
                    self.current_song[member.guild.id] = None
                    await voice.disconnect()

        elif after.channel is not None and before.channel is None and voice and voice.channel == after.channel:
            if len(after.channel.members) > 2:
                return
            
    def format_duration(self, duration):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"

    async def create_embed(self, song_info, ctx, description):
        embed = discord.Embed(
            title=(f":musical_note: {song_info['title']}"),
            description=description,
            url=song_info.get('webpage_url', song_info.get('url', '')),
            color=discord.Color.blue()
        )
        embed.add_field(name="영상 길이", value=self.format_duration(song_info['duration']), inline=True)
        embed.add_field(name="채널", value=song_info['uploader'], inline=True)
        embed.add_field(name="대기열 순서", value=f"{song_info['queue_position'] + 1}번째", inline=True)
        embed.set_thumbnail(url=song_info['thumbnail'])
        embed.set_footer(text=f"요청자 : {song_info['requester']}")
        return embed
    
    Music = discord.SlashCommandGroup("음악")

    @Music.command(name="검색", description="YouTube에서 음악을 지정한 개수만큼 검색합니다.", options=[
        discord.Option(str, name="제목", description="검색할 음악의 제목", required=True),
        discord.Option(int, name="개수", description="검색할 개수 (1 ~ 10, 기본값: 5, 선택)", required=False, min_value=1, max_value=10, default=5)])
    async def search(self, ctx, *, query: str, index: int):
        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 검색 중입니다..."))
        print(f"[Command | Music] 사용자가 음악 검색을 요청했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 키워드: {query}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        try:
            with yt_dlp.YoutubeDL(self.YDL_OPT) as ydl:
                search_query = f"ytsearch{index}:{query}"
                info = await asyncio.get_running_loop().run_in_executor(None, lambda: ydl.extract_info(search_query, download=False))
                if not info['entries']:
                    return await ctx.send(embed=discord.Embed(description=f":warning: {query}에 대한 검색 결과가 없습니다."))
                
                embed = discord.Embed(title=f":notes: {query}에 대한 검색 결과", color=discord.Color.blue())
                for index, entry in enumerate(info['entries']):
                    embed.add_field(name=f"{index + 1}. {entry.get('title')}", value=f"채널: {entry.get('uploader')}, 음악 길이: {self.format_duration(entry.get('duration'))}", inline=False)

                await ctx.send(content=":white_check_mark: 30초 내에 번호를 입력하여 해당 음악을 재생할 수 있습니다.", embed=embed)
                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= len(info['entries'])
                
                try:
                    message = await self.bot.wait_for('message', check=check, timeout=30)
                    index = int(message.content) - 1
                    await self.play(ctx, song=info['entries'][index]['webpage_url'])
                except asyncio.TimeoutError:
                    return await ctx.send(embed=discord.Embed(description=":white_check_mark: 시간 내에 음악을 선택하지 않아 음악 재생이 취소되었습니다."))
                except Exception as e:
                    await ctx.send(embed=discord.Embed(description=f":warning: 음악을 재생하는 중 예상치 못한 오류가 발생했습니다. (로그: {e})"))
                    print(f"[Error | Music] 음악을 재생하는 중 오류가 발생했습니다. (서버: {ctx.guild.name}, 로그: {(e)}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except yt_dlp.utils.DownloadError as e:
            await ctx.send(embed=discord.Embed(description=f":warning: 음악을 검색하는 중 예상치 못한 오류가 발생했습니다. (로그: {e})"))
            print(f"[Error | Music] 음악을 검색하는 중 오류가 발생했습니다. (서버: {ctx.guild.name}, 로그: {(e)}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except Exception as e:
            await ctx.send(embed=discord.Embed(description=f":warning: 예상치 못한 오류가 발생했습니다. (로그: {e})"))
            print(f"[Error | Music] 예상치 못한 오류가 발생했습니다. (서버: {ctx.guild.name}, 로그: {(e)}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    @Music.command(name="재생", description="YouTube에서 음악을 검색하여 재생합니다.", options=[
        discord.Option(str, name="제목", description="재생할 음악의 제목", required=True)])
    async def play(self, ctx, *, song):
        if not ctx.author.voice:
            return await ctx.respond(embed=discord.Embed(description=":warning: 음악을 재생하려면 먼저 사용자가 음성 채널에 연결해야 합니다."), ephemeral=True)
        
        voice_channel = ctx.author.voice.channel

        if ctx.voice_client is not None and ctx.voice_client.channel != voice_channel:
            return await ctx.respond(embed=discord.Embed(description=":warning: 클라이언트가 같은 서버의 다른 음성 채널에 연결되어 있습니다. 클라이언트의 연결을 끊거나 기다린 후 다시 시도하십시오."), ephemeral=True)
        
        try:
            voice = ctx.voice_client or await voice_channel.connect()
        except Exception as e:
            print(f"[Error | Music] 음성 채널에 연결하는 중 오류가 발생했습니다. (서버: {ctx.guild.name}, 로그: {(e)}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
            return await ctx.respond(fembed=discord.Embed(description=":warning: 음성 채널에 연결하는 중 예상치 못한 오류가 발생했습니다. {(e)}"), ephemeral=True)

        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 불러오는 중입니다..."))
        try:
            with yt_dlp.YoutubeDL(self.YDL_OPT) as ydl:
                info = await asyncio.get_running_loop().run_in_executor(None, lambda: ydl.extract_info(f"ytsearch1:{song}", download=False))

                if not info['entries']:
                    return await ctx.respond(f"**오류:** {song}에 대한 검색 결과가 없습니다.")

                song_info = {
                    "url": info['entries'][0].get('url'),
                    "webpage_url": info['entries'][0].get("webpage_url"),
                    "title": info['entries'][0]["title"],
                    "duration": info['entries'][0]["duration"],
                    "uploader": info['entries'][0]["uploader"],
                    "thumbnail": info['entries'][0]["thumbnail"],
                    "requester": str(ctx.author),
                    "queue_position": len(self.queue)
                }

                if song_info not in self.queue:
                    self.queue.append(song_info)
                description = f"**{song_info['title']}** 음악을 {'재생하고 있습니다.' if len(self.queue) == 1 and not voice.is_playing() and not voice.is_paused() else '재생 목록에 추가했습니다.'}"
                embed = await self.create_embed(song_info, ctx, description)
                print(f"[Command | Music] 사용자가 음악 재생을 요청했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 음악: {song_info['title']}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

                if ctx.guild.id not in self.current_volume:
                    self.current_volume.get(ctx.guild.id, 0.5)

                if len(self.queue) == 1 and not voice.is_playing() and not voice.is_paused():
                    self.queue.pop(0)
                    self.current_volume.get(ctx.guild.id, 0.5)
                    voice.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(song_info['url'], **self.FFMPEG_OPT),
                                                            volume=self.current_volume.get(ctx.guild.id, 0.5)),
                                                            after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(ctx, voice, song_info), self.bot.loop))
                    self.previous_song[ctx.guild.id] = self.current_song.get(ctx.guild.id)
                    self.current_song[ctx.guild.id] = song_info
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(embed=embed)

        except yt_dlp.utils.DownloadError as e:
            await ctx.respond(f"**오류:** 음악을 다운로드하는 중 예상치 못한 오류가 발생했습니다. ({e})")
            print(f"[Error | Music] 음악을 다운로드하는 중 오류가 발생했습니다. (서버: {ctx.guild.name}, 로그: {(e)}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except Exception as e:
            await ctx.send(f"**오류:** 예상치 못한 오류가 발생했습니다. ({e})")
            print(f"[Error | Music] 예상치 못한 오류가 발생했습니다. (서버: {ctx.guild.name}, 로그: {(e)}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    async def play_next(self, ctx, voice, Audio_Source):
        if self.loop.get(ctx.guild.id, True) and self.current_song.get(ctx.guild.id):
            self.queue.insert(0, self.current_song[ctx.guild.id])

        if not self.queue:
            if self.queue_loop.get(ctx.guild.id, True) and self.current_song.get(ctx.guild.id):
                self.queue.append(self.current_song[ctx.guild.id])
            else:
                return await self.cleanup(voice, ctx.guild.id)
            
        if (self.queue or self.loop.get(ctx.guild.id, True)) and not voice.is_playing() and not voice.is_paused():
            song_info = self.queue.pop(0) if self.queue else self.current_song[ctx.guild.id]

            if self.queue_loop.get(ctx.guild.id, True) and not self.loop.get(ctx.guild.id, True):
                self.queue.append(song_info)
            self.current_volume.get(ctx.guild.id, 0.5)
            voice.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(song_info['url'], **self.FFMPEG_OPT),
                                                    volume=self.current_volume.get(ctx.guild.id, 0.5)),
                                                    after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(ctx, voice, song_info), self.bot.loop))
            self.previous_song[ctx.guild.id] = self.current_song.get(ctx.guild.id)
            self.current_song[ctx.guild.id] = song_info

            if not self.loop.get(ctx.guild.id, True) and not self.queue_loop.get(ctx.guild.id, True):
                embed = await self.create_embed(song_info, ctx, f"**{song_info['title']}** 음악을 재생하고 있습니다.")
                print(f"[Command | Music] 사용자가 음악 재생을 요청했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 음악: {song_info['title']}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
                await ctx.send(embed=embed)

        if not self.queue and not voice.is_playing():
            await self.cleanup(voice, ctx.guild.id)

    async def cleanup(self, voice, guild_id):
        voice.stop()
        self.queue.clear()
        self.current_song[guild_id] = None
        await voice.disconnect()
        
    @Music.command(name="정보", description="현재 재생 중인 음악의 정보를 표시합니다.")
    async def now(self, ctx):
        song_info = self.current_song.get(ctx.guild.id)

        if song_info:
            embed = await self.create_embed(song_info, ctx, f"**{song_info['title']}** 음악을 재생하고 있습니다.")
            print(f"[Command | Music] 사용자가 음악 정보를 요청했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 음악: {song_info['title']}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
            await ctx.respond(embed=embed)
        else:
            await ctx.respond(embed=discord.Embed(description=":warning: 음악 정보를 표시하려면 음악이 재생 중이여야 합니다."), ephemeral=True)

    Queue = Music.create_subgroup("대기열", "대기열 관련 명령어입니다.")

    @Queue.command(name="다음곡", description="현재 재생 중인 음악을 건너 뜁니다. 음성 채널에 사용자가 2명 이상이라면 건너뛰기 투표를 진행합니다.")
    async def skip(self, ctx):
        if not ctx.guild.voice_client or not ctx.guild.voice_client.is_playing():
            return await ctx.respond(embed=discord.Embed(description=":warning: 음악을 건너 뛰려면 음악이 재생 중이여야 합니다."), ephemeral=True)

        if len([m for m in ctx.author.voice.channel.members if not m.bot]) <= 1:
            ctx.guild.voice_client.stop()
            await ctx.respond(embed=discord.Embed(description=":white_check_mark: 재생 중인 음악을 건너뛰기했습니다."))
            return print(f"[Command | Music] 사용자가 음악을 건너뛰기했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

        view = SkipVoteView()
        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 음성 채널에 사용자가 2명 이상이므로 건너뛰기 투표를 시작합니다. 현재 곡을 건너뛰려면 30초 내에 ✅ 투표를 추가하십시오. 사용자의 반 이상이 찬성할 시 음악을 건너뛰기합니다.", view=view))
        await view.wait()

        require_votes = len([m for m in ctx.author.voice.channel.members if not m.bot]) // 2
        if view.get_votes() >= require_votes:
            ctx.guild.voice_client.stop()
            await self.play_next(ctx, ctx.guild.voice_client, None)
            await ctx.channel.send(embed=discord.Embed(description=":white_check_mark: 사용자의 반 이상이 찬성했으므로 음악을 건너 뜁니다."))
            print(f"[Command | Music] 사용자가 음악을 건너뛰기했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        else:
            await ctx.channel.send(embed=discord.Embed(description=f":white_check_mark: 사용자의 반 이상이 찬성하지 않아 음악을 건너뛰지 않습니다. (필요: {require_votes}표, 현재: {view.get_votes()}표)"))

    @Queue.command(name="이전곡", description="대기열에서 현재 재생 중인 곡의 이전 곡을 재생합니다.")
    async def previous(self, ctx):
        previous_song = self.previous_song.get(ctx.guild.id)

        if previous_song is None:
            return await ctx.respond(embed=discord.Embed(description=":warning: 이전에 재생된 곡이 없습니다."), ephemeral=True)

        if not ctx.author.voice:
            return await ctx.respond(embed=discord.Embed(description=":warning: 먼저 음성 채널에 접속해 주세요."), ephemeral=True)

        voice = ctx.voice_client or await ctx.author.voice.channel.connect()

        if voice.is_playing() or voice.is_paused():
            voice.stop()

        self.previous_song[ctx.guild.id] = self.current_song.get(ctx.guild.id)
        self.current_song[ctx.guild.id] = previous_song

        voice.play(discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(previous_song["url"], **self.FFMPEG_OPT),
            volume=self.current_volume.get(ctx.guild.id, 0.5)
        ), after=lambda e: asyncio.run_coroutine_threadsafe(
            self.play_next(ctx, voice, previous_song), self.bot.loop
        ))

        embed = await self.create_embed(previous_song, ctx, f"**{previous_song['title']}** 음악을 재생하고 있습니다.")
        await ctx.respond(embed=embed)

    def queue_page(self, ctx, queue, page_num, songs_per_page=10):
        start_index = (page_num - 1) * songs_per_page
        end_index = min(start_index + songs_per_page, len(self.queue))
        
        if start_index >= len(self.queue):
            return None, None

        current_song_info = self.current_song.get(ctx.guild.id)
        embed = discord.Embed(title=":notes: 대기열을 표시합니다.", description="현재 대기열 목록:", color=discord.Color.blue())
        embed.add_field(name=f"현재 재생 중: {current_song_info['title']}", value=f"영상 길이: {self.format_duration(current_song_info['duration'])} | 요청자: {current_song_info['requester']}", inline=False)
        for index in range(start_index, end_index):
            song_info = self.queue[index]
            formatted_duration = self.format_duration(song_info['duration'])
            requester = song_info['requester']
            embed.add_field(name=f"{index + 1}. {song_info['title']}", value=f"영상 길이: {formatted_duration} | 요청자: {requester}", inline=False)

        total_pages = (len(self.queue) + songs_per_page - 1) // songs_per_page
        embed.set_footer(text=f"페이지: {page_num} / {total_pages}")
        return embed, total_pages

    class queueView(View):
        def __init__(self, queue, initial_page=1):
            super().__init__()
            self.queue = queue
            self.Cur_Page = initial_page
            self.total_pages = (len(queue) + 9) // 10 
            self.update_buttons()

        def update_buttons(self):
            self.clear_items()

            first_button = Button(style=ButtonStyle.secondary, emoji="⏪", disabled=self.Cur_Page <= 1)
            prev_button = Button(style=ButtonStyle.secondary, emoji="⬅️", disabled=self.Cur_Page <= 1)
            next_button = Button(style=ButtonStyle.secondary, emoji="➡️", disabled=self.Cur_Page == self.total_pages)
            last_button = Button(style=ButtonStyle.secondary, emoji="⏩", disabled=self.Cur_Page == self.total_pages)

            first_button.callback = self.go_to_first_page
            prev_button.callback = self.go_to_prev_page
            next_button.callback = self.go_to_next_page
            last_button.callback = self.go_to_last_page

            self.add_item(first_button)
            self.add_item(prev_button)
            self.add_item(next_button)
            self.add_item(last_button)

        async def update_embed(self, interaction):
            embed, _ = self.queue_page(self.queue, self.Cur_Page)
            self.update_buttons()
            await interaction.response.edit_message(embed=embed, view=self)

        async def go_to_first_page(self, interaction):
            self.Cur_Page = 1
            await self.update_embed(interaction)

        async def go_to_prev_page(self, interaction):
            if self.Cur_Page > 1:
                self.Cur_Page -= 1
                await self.update_embed(interaction)
            else:
                await interaction.response.defer()

        async def go_to_next_page(self, interaction):
            self.Cur_Page += 1
            await self.update_embed(interaction)

        async def go_to_last_page(self, interaction):
            self.Cur_Page = self.total_pages
            await self.update_embed(interaction)

    @Queue.command(name="목록", description="대기열 목록을 표시합니다.")
    async def queue(self, ctx):
        if not self.queue:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열이 비어 있습니다. 대기열 관련 기능을 사용하려면 대기열에 음악을 추가해야 합니다."), ephemeral=True)

        embed, total_pages = self.queue_page(ctx, ctx.guild.id, 1)
        if embed is None:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열을 표시하는 중 알 수 없는 오류가 발생했습니다."), ephemeral=True)

        view = self.queueView(self.queue)
        view.total_pages = total_pages
        view.update_buttons()
        await ctx.respond(embed=embed, view=view)
        print(f"[Command | Music] 사용자가 대기열을 요청했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    @Queue.command(name="초기화", description="대기열을 초기화합니다.")
    async def queue_clear(self, ctx):
        if not self.queue:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열이 비어 있습니다. 대기열 관련 기능을 사용하려면 대기열에 음악을 추가해야 합니다."), ephemeral=True)

        self.queue.clear()
        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 대기열을 초기화했습니다."))
        print(f"[Command | Music] 사용자가 대기열을 초기화했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    @Queue.command(name="삭제", description="대기열에서 음악을 삭제합니다.", options=[
        discord.Option(int, name="번호", description="삭제할 음악의 번호", required=True)])
    async def queue_delete(self, ctx, position: int):
        if not self.queue:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열이 비어 있습니다. 대기열 관련 기능을 사용하려면 대기열에 음악을 추가해야 합니다."), ephemeral=True)

        if position <= 0 or position > len(self.queue):
            return await ctx.respond(fembed=discord.Embed(description=":warning: 올바른 번호를 입력하세요. (1 ~ {len(self.queue)})"), ephemeral=True)

        try:
            removed_song = self.queue.pop(position - 1)
            await ctx.respond(embed=discord.Embed(description=f":white_check_mark: {removed_song.get('title')} 음악을 대기열에서 삭제했습니다."))
            print(f"[Music] 사용자가 대기열에서 음악을 삭제했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        except IndexError:
             return await ctx.respond(fembed=discord.Embed(description=":warning: 올바른 번호를 입력하세요. (1 ~ {len(self.queue) + 1})"), ephemeral=True)

    @Queue.command(name="재생", description="대기열에서 원하는 음악을 선택하여 재생합니다.", options=[
        discord.Option(int, name="번호", description="재생할 음악의 번호", required=True)])
    async def queue_play(self, ctx, index: int):
        if not self.queue:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열이 비어 있어 번호로 재생할 수 없습니다."), ephemeral=True)
        
        if index < 1 or index > len(self.queue):
            return await ctx.respond(fembed=discord.Embed(description=":warning: 올바른 번호를 입력하세요. (1 ~ {len(self.queue)})"), ephemeral=True)

        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        if voice_channel is None:
            return await ctx.respond(embed=discord.Embed(description=":warning: 음성 채널에 먼저 접속해 주세요."), ephemeral=True)

        voice = ctx.voice_client or await voice_channel.connect()

        if voice.is_playing() or voice.is_paused():
            voice.stop()

        index = index - 1
        song_info = self.queue.pop(index)
        self.current_song[ctx.guild.id] = song_info

        voice.play(discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(song_info['url'], **self.FFMPEG_OPT),
            volume=self.current_volume.get(ctx.guild.id, 0.5)),
            after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(ctx, voice, song_info), self.bot.loop)
        )

        embed = await self.create_embed(song_info, ctx, f"**{song_info['title']}** 음악을 재생하고 있습니다.")
        await ctx.respond(embed=embed)

    @Music.command(name="반복", description="현재 음악을 반복할 옵션을 선택합니다.", options=[
        discord.Option(str, name="모드", description="반복 모드", choices=["재생목록", "단일", "끄기"], required=True)])
    async def loop(self, ctx, mode: str):
        if mode.lower() in ["재생목록"]:
            self.queue_loop[ctx.guild.id] = True
            self.loop[ctx.guild.id] = False
            if self.current_song.get(ctx.guild.id) is not None:
                self.queue.append(self.current_song[ctx.guild.id])
            await ctx.respond(embed=discord.Embed(description=":white_check_mark: 음악 반복 재생 모드를 전체 반복으로 설정했습니다."))
        elif mode.lower() in ["단일"]:
            self.queue_loop[ctx.guild.id] = False
            self.loop[ctx.guild.id] = True
            if self.current_song.get(ctx.guild.id) is not None:
                self.queue.insert(0, self.current_song[ctx.guild.id])
            await ctx.respond(embed=discord.Embed(description=":white_check_mark: 음악 반복 재생 모드를 단일 반복으로 설정했습니다."))
        elif mode.lower() in ["끄기"]:
            self.queue_loop[ctx.guild.id] = False
            self.loop[ctx.guild.id] = False
            await ctx.respond(embed=discord.Embed(description=":white_check_mark: 음악 반복 재생 모드를 해제했습니다."))

    @Music.command(name="종료", description="현재 재생 중인 음악을 종료합니다.")
    async def stop(self, ctx):
        if not ctx.voice_client:
            return await ctx.respond(embed=discord.Embed(description=":warning: 음악을 종료하려면 먼저 음악이 재생 중이여야 합니다."))
        
        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            ctx.voice_client.stop()
            self.queue.clear()
            self.current_song[ctx.guild.id] = None
            try:
                await ctx.voice_client.disconnect()
            except Exception as e:
                print(f"[Music] 음성 채널의 연결을 해제하는 중 예상치 못한 오류가 발생했습니다. (서버: {ctx.guild.name}, 로그: {(e)}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
            print(f"[Music] 사용자가 음악을 종료했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
            return await ctx.respond(embed=discord.Embed(description=":white_check_mark: 재생 중인 음악을 종료하고 대기열을 초기화했습니다."))
        
        await ctx.respond(embed=discord.Embed(description=":warning: 음악을 종료하려면 먼저 음악이 재생 중이여야 합니다."))

    @Music.command(name="일시정지", description="현재 재생 중인 음악을 일시 정지합니다.")
    async def pause(self, ctx):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await ctx.respond(embed=discord.Embed(description=":white_check_mark: 음악을 일시 정지하려면 먼저 음악이 재생 중이여야 합니다."))
        
        ctx.voice_client.pause()
        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 재생 중인 음악을 일시 정지했습니다."))

    @Music.command(name="재개", description="일시 정지한 음악을 재개합니다.")
    async def resume(self, ctx):
        if not ctx.voice_client or ctx.voice_client.is_playing():
            return await ctx.respond(embed=discord.Embed(description=":warning: 음악이 일시 정지되어 있지 않거나 음악이 재생 중이 아닙니다."), ephemeral=True)

        ctx.voice_client.resume()
        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 일시 정지한 음악을 재개했습니다."))

    @Music.command(name="볼륨", description="현재 재생 중인 음악의 볼륨을 조절합니다.", options=[
        discord.Option(float, name="크기", description="볼륨 크기 (0~500)", required=True, min_value=0, max_value=500)])
    async def volume(self, ctx, vol: float):
        if ctx.voice_client is None:
            return await ctx.respond(embed=discord.Embed(description=":warning: 음악의 볼륨을 조절하려면 먼저 음악이 재생 중이여야 합니다."), ephemeral=True)

        if not 0 <= vol <= 500:
            return await ctx.respond(embed=discord.Embed(description=":warning: 0에서 500 사이의 정수를 입력하세요."), ephemeral=True)
        self.current_volume[ctx.guild.id] = (vol / 100) * 0.5

        if isinstance(ctx.voice_client.source, discord.PCMVolumeTransformer):
            ctx.voice_client.source.volume = self.current_volume[ctx.guild.id]
            await ctx.respond(embed=discord.Embed(description=f":white_check_mark: 애플리케이션의 볼륨을 {vol}%로 설정했습니다."))
        else:
            await ctx.respond(embed=discord.Embed(description=":warning: 애플리케이션의 볼륨을 조절하는 데 실패했습니다."))

    @Music.command(name="셔플", description="대기열을 셔플합니다.")
    async def shuffle(self, ctx):
        print(f"[Command | Music] 사용자가 대기열 셔플을 요청했습니다. (요청자: {ctx.author.name}, 서버: {ctx.guild.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

        if len(self.queue) < 2:
            return await ctx.respond(embed=discord.Embed(description=":warning: 대기열 셔플을 사용하려면 먼저 대기열에 음악을 2개 이상 추가해야 합니다."), ephemeral=True)
            
        random.shuffle(self.queue)
        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 대기열을 셔플했습니다. 셔플된 대기열을 /음악 대기열 명령어로 확인하세요."))
    
def setup(bot):
    bot.add_cog(music(bot))