import discord, os
from Token import APP_TOKEN

bot = discord.Bot(intents=discord.Intents.all())

# Cogs 불러오기
for filename in os.listdir('./Cogs'):
    if filename.endswith('.py'):
        bot.load_extension(f'Cogs.{filename[:-3]}')

bot.run(APP_TOKEN)