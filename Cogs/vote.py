import discord
import asyncio
import datetime
import re
from discord.ext import commands, tasks
from discord.ui import View, Button

class VoteView(discord.ui.View):
    def __init__(self, poll_name, options, duration, author):
        super().__init__(timeout=duration)
        self.poll_name = poll_name
        self.options = options
        self.votes = {option: [] for option in options}
        self.author = author
        self.start_time = datetime.datetime.now()
        self.ended = False

        for option in options:
            self.add_item(VoteButton(option))

    async def update_embed(self, interaction: discord.Interaction):
        if self.ended:
            return
        
        total_votes = sum(len(voters) for voters in self.votes.values())

        embed = discord.Embed(title=f":ballot_box: {self.poll_name}", description=f"투표가 진행 중입니다. | 현재 총 투표 수: **{total_votes}명**", color=discord.Color.blue())
        embed.set_footer(text=f"투표 요청자: {self.author.display_name}")

        for option, voters in self.votes.items():
            percent = (len(voters) / total_votes * 100) if total_votes > 0 else 0
            embed.add_field(name=f"{option}", value=f"{len(voters)}표 ({percent:.1f}%)", inline=False)

        await interaction.message.edit(embed=embed, view=self)

    async def end_poll(self):
        if self.ended:
            return
        self.ended = True

        total_votes = sum(len(voters) for voters in self.votes.values())

        embed = discord.Embed(title=f":ballot_box: {self.poll_name}", description=f"투표가 종료되었습니다. | 총 투표 수: **{total_votes}명**", color=discord.Color.blue())
        embed.set_footer(text=f"투표 요청자: {self.author.display_name}")
        
        for option, voters in self.votes.items():
            percent = (len(voters) / total_votes * 100) if total_votes > 0 else 0
            embed.add_field(name=f"{option}", value=f"{len(voters)}표 ({percent:.1f}%)", inline=False)

        for item in self.children:
            item.disabled = True
        await self.message.edit(embed=embed, view=self)
        await self.message.channel.send(embed=embed)

    async def on_timeout(self):
        await self.end_poll()

class VoteButton(discord.ui.Button):
    def __init__(self, label):
        super().__init__(label=label, style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        view: VoteView = self.view

        for option, voters in view.votes.items():
            if interaction.user.id in voters:
                if option == self.label:
                    return await interaction.response.send_message(embed=discord.Embed(description=f":warning: 이미 {self.label}에 투표했습니다."), ephemeral=True)
                else:
                    voters.remove(interaction.user.id)

        view.votes[self.label].append(interaction.user.id)
        await interaction.response.send_message(embed=discord.Embed(description=f":white_check_mark: {self.label}에 투표했습니다."), ephemeral=True)
        print(f"[Vote] 사용자가 {self.label}에 투표했습니다. (서버: {interaction.guild.name}, 요청자: {interaction.user.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        await view.update_embed(interaction)

class vote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_polls = {}

    Vote = discord.SlashCommandGroup("투표")

    @Vote.command(name="생성", description="투표를 생성합니다.", options=[
        discord.Option(str, name="이름", description="투표 이름", required=True),
        discord.Option(str, name="시간", description="투표 지속 시간 (ex: 10초, 5분, 2시간, 1일, 4주, 1년)", required=True),
        discord.Option(str, name="1", description="선택지 1", required=True),
        discord.Option(str, name="2", description="선택지 2", required=True),
        discord.Option(str, name="3", description="선택지 3", required=False),
        discord.Option(str, name="4", description="선택지 4", required=False),
        ])
    async def create_vote(self, ctx, name: str, duration: str, field1: str, field2: str, field3: str = None, field4: str = None):
        match = re.match(r"(\d+)\s*(초|분|시간|일|주|년)", duration)
        if not match:
            return await ctx.respond(
                embed=discord.Embed(description=":warning: 올바른 기간 형식이 아닙니다. (ex: 10초, 5분, 2시간, 1일, 4주, 1년)"), ephemeral=True,)

        value = int(match.group(1))
        unit = match.group(2)

        if unit == "초": duration = datetime.timedelta(seconds=value)
        elif unit == "분": duration = datetime.timedelta(minutes=value)
        elif unit == "시간": duration = datetime.timedelta(hours=value)
        elif unit == "일": duration = datetime.timedelta(days=value)
        elif unit == "주": duration = datetime.timedelta(weeks=value)
        elif unit == "년": duration = datetime.timedelta(days=365*value)

        if duration.total_seconds() < 30:
            return await ctx.respond(embed=discord.Embed(description=":warning: 투표 시간은 30초보다 길어야 합니다."), ephemeral=True)
        
        options = [o for o in [field1, field2, field3, field4] if o]
        if len(options) < 2:
            return await ctx.respond(embed=discord.Embed(description=":warning: 선택지는 최소 2개 이상이어야 합니다."), ephemeral=True)
        
        embed = discord.Embed(
            title=f":ballot_box: {name}",
            description=f"투표가 진행 중입니다. | 현재 총 투표 수: **0명**",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"투표 요청자: {ctx.author.display_name}")

        for option in options:
            embed.add_field(name=f"{option}", value=f"0표 (0%)", inline=False)

        view = VoteView(name, options, duration.total_seconds(), ctx.author)
        message = await ctx.respond(embed=embed, view=view)
        view.message = await message.original_response()
        print(f"[Command | Vote] 사용자가 투표를 생성했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

        self.active_polls[ctx.author.id] = view
        await asyncio.sleep(duration.total_seconds())
        await view.on_timeout()

    @Vote.command(name="종료", description="사용자가 생성한 투표를 종료합니다.")
    async def end_vote(self, ctx):
        view = self.active_polls.get(ctx.author.id)
        if not view:
            return await ctx.respond(embed=discord.Embed(description=":warning: 진행 중인 직접 생성한 투표가 없습니다."), ephemeral=True)

        await view.end_poll()
        self.active_polls.pop(ctx.author.id, None)
        await ctx.respond(embed=discord.Embed(description=":white_check_mark: 투표를 종료했습니다."), ephemeral=True)
        print(f"[Command | Vote] 사용자가 투표를 종료했습니다. (서버: {ctx.guild.name}, 요청자: {ctx.author.name}, 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

def setup(bot):
    bot.add_cog(vote(bot))