import discord
import os
from dotenv import load_dotenv

from discord.ext import tasks

load_dotenv()

TOKEN = os.environ['TOKEN']

intents = discord.Intents.default()
# Enable the message content intent (if you need to read message content)
# very important
intents.message_content = True 
client = discord.Client(intents=intents)

# Event that runs when the bot is ready
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

# Event that runs when a message is received
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!hello'):
        await message.channel.send('Hello there!')
    
    if message.content.startswith('!ping'):
        await message.channel.send(f'Pong! Latency: {round(client.latency * 1000)}ms')

client.run(TOKEN)