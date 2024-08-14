
import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import urllib.parse
import urllib.request
import re


def MusicBot():
    load_dotenv()
    TOKEN = os.getenv('CLIENT_TOKEN')
    intents = discord.Intents.default()
    intents.message_content = True
    client = commands.Bot(command_prefix=".", intents=intents)

    queues = {}
    voice_clients = {}
    youtube_base_url = 'https://www.youtube.com/'
    youtube_results_url = youtube_base_url + 'results?'
    youtube_watch_url = youtube_base_url + 'watch?v='
    yt_dl_options = {"format": "bestaudio/best"}
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                      'options': '-vn -filter:a "volume=0.25"'}

    @client.event
    async def on_ready():
        print(f'{client.user} is now jamming')
        try:
            synced = await client.tree.sync()
            print(f"Synced {len(synced)} commands")
        except Exception as e:
            print(e)

    async def play_next(ctx):
        if queues[ctx.guild.id] != []:
            link = queues[ctx.guild.id].pop(0)
            await play(ctx, link=link)

    @client.tree.command(name="play", description="Plays a song from YouTube")
    async def play(interaction: discord.Interaction, *, link: str):
        ctx = await client.get_context(interaction)
        try:
            voice_client = await interaction.user.voice.channel.connect()
            voice_clients[voice_client.guild.id] = voice_client
            await interaction.response.send_message(f"Teraz gramy: {link}")
        except Exception as e:
            print(e)

        try:
            if youtube_base_url not in link:
                query_string = urllib.parse.urlencode({'search_query': link})
                content = urllib.request.urlopen(
                    youtube_results_url + query_string)
                search_results = re.findall(
                    r'/watch\?v=(.{11})', content.read().decode())
                link = youtube_watch_url + search_results[0]

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))

            song = data['url']
            player = discord.FFmpegOpusAudio(song, **ffmpeg_options)

            voice_clients[interaction.guild.id].play(
                player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
        except Exception as e:
            print(e)

    @client.tree.command(name="clear_queue", description="Clears the queue")
    async def clear_queue(interaction: discord.Interaction):
        if interaction.guild.id in queues:
            queues[interaction.guild.id].clear()
            await interaction.response.send_message("Queue cleared!")
        else:
            await interaction.response.send_message("There is no queue to clear")

    @client.tree.command(name="pause", description="Pauses the current song")
    async def pause(interaction: discord.Interaction):
        try:
            voice_clients[interaction.guild.id].pause()
            await interaction.response.send_message("Paused!")
        except Exception as e:
            print(e)

    @client.tree.command(name="resume", description="Resumes the current song")
    async def resume(interaction: discord.Interaction):
        try:
            voice_clients[interaction.guild.id].resume()
            await interaction.response.send_message("Resumed!")
        except Exception as e:
            print(e)

    @client.tree.command(name="stop", description="Stops the player")
    async def stop(interaction: discord.Interaction):
        try:
            voice_clients[interaction.guild.id].stop()
            await voice_clients[interaction.guild.id].disconnect()
            del voice_clients[interaction.guild.id]
            await interaction.response.send_message("Stopped and disconnected!")
        except Exception as e:
            print(e)

    @client.tree.command(name="queue", description="Adds a song to the queue")
    async def queue(interaction: discord.Interaction, *, url: str):
        if interaction.guild.id not in queues:
            queues[interaction.guild.id] = []
        queues[interaction.guild.id].append(url)
        await interaction.response.send_message("Added to queue!")

    client.run(TOKEN)
