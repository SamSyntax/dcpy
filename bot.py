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
    inactivity_timers = {}
    voice_clients = {}
    youtube_base_url = 'https://www.youtube.com/'
    youtube_results_url = youtube_base_url + 'results?'
    youtube_watch_url = youtube_base_url + 'watch?v='
    yt_dl_options = {"format": "bestaudio/best"}
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
        'options': '-vn -loglevel panic'
    }

    @client.event
    async def on_ready():
        print(f'{client.user} is now jamming')
        try:
            synced = await client.tree.sync()
            print(f"Synced {len(synced)} commands")
        except Exception as e:
            print(e)

    @client.event
    async def on_guild_join(guild):
        """Initialize queue for the guild when the bot joins it."""
        queues[guild.id] = []

    async def play_next(ctx):
        if queues[ctx.guild.id]:
            next_song = queues[ctx.guild.id].pop(0)
            await play_song(ctx, next_song)

    async def start_inactivity_timer(ctx):
        await asyncio.sleep(10)
        if ctx.guild.id in voice_clients and not voice_clients[ctx.guild.id].is_playing():
            await voice_clients[ctx.guild.id].disconnect()
            del voice_clients[ctx.guild.id]
            del inactivity_timers[ctx.guild.id]
            print(f"Disconnected from {ctx.guild.name} due to inactivity.")

    async def reset_inactivity_timer(ctx):
        if ctx.guild.id in inactivity_timers:
            inactivity_timers[ctx.guild.id].cancel()
        inactivity_timers[ctx.guild.id] = asyncio.create_task(
            start_inactivity_timer(ctx))

    async def play_song(ctx, link: str, retries=3):
        """Plays a song with retry logic."""
        attempt = 0
        while attempt < retries:
            try:
                if youtube_base_url not in link:
                    query_string = urllib.parse.urlencode(
                        {'search_query': link})
                    content = urllib.request.urlopen(
                        youtube_results_url + query_string)
                    search_results = re.findall(
                        r'/watch\?v=(.{11})', content.read().decode())
                    link = youtube_watch_url + search_results[0]

                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))

                if 'url' not in data:
                    await ctx.send("Nie udało się pobrać linku do piosenki.")
                    return

                song_url = data['url']
                player = discord.FFmpegOpusAudio(song_url, **ffmpeg_options)

                if ctx.guild.id in voice_clients and voice_clients[ctx.guild.id].is_playing():
                    queues[ctx.guild.id].append(link)
                    embed = discord.Embed(
                        title="Dodano do kolejki", description=link, color=discord.Color.blue())
                    await ctx.send(embed=embed)
                else:
                    voice_clients[ctx.guild.id].play(
                        player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
                    embed = discord.Embed(
                        title="Teraz gramy", description=link, color=discord.Color.green())
                    await ctx.send(embed=embed)
                break
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                attempt += 1
                if attempt >= retries:
                    embed = discord.Embed(
                        title="Błąd", description="Nie udało się odtworzyć piosenki po kilku próbach.", color=discord.Color.red())
                    await ctx.send(embed=embed)
                else:
                    await asyncio.sleep(2)

    @client.tree.command(name="play", description="Plays a song from YouTube")
    async def play(interaction: discord.Interaction, *, link: str):
        await interaction.response.defer()
        ctx = await client.get_context(interaction)
        if interaction.guild.id not in queues:
            queues[interaction.guild.id] = []

        if interaction.guild.id not in voice_clients:
            try:
                voice_client = await interaction.user.voice.channel.connect()
                voice_clients[interaction.guild.id] = voice_client
            except Exception as e:
                print(e)
                embed = discord.Embed(
                    title="Błąd", description="Nie mogę dołączyć do kanału głosowego.", color=discord.Color.red())
                await interaction.followup.send(embed=embed)
                return

        if not voice_clients[interaction.guild.id].is_playing():
            await play_song(ctx, link)
            embed = discord.Embed(
                title="Odtwarzanie", description="Teraz gramy!", color=discord.Color.green())
            await interaction.followup.send(embed=embed)
        else:
            queues[interaction.guild.id].append(link)
            embed = discord.Embed(title="Dodano do kolejki",
                                  description=link, color=discord.Color.blue())
            await interaction.followup.send(embed=embed)
        await reset_inactivity_timer(ctx)

    @client.tree.command(name="clear_queue", description="Clears the queue")
    async def clear_queue(interaction: discord.Interaction):
        if interaction.guild.id in queues:
            queues[interaction.guild.id].clear()
            embed = discord.Embed(
                title="Kolejka", description="Kolejka została wyczyszczona!", color=discord.Color.blue())
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="Kolejka", description="Brak kolejki do wyczyszczenia.", color=discord.Color.yellow())
            await interaction.response.send_message(embed=embed)

    @client.tree.command(name="pause", description="Pauses the current song")
    async def pause(interaction: discord.Interaction):
        try:
            if interaction.guild.id in voice_clients and voice_clients[interaction.guild.id].is_playing():
                voice_clients[interaction.guild.id].pause()
                embed = discord.Embed(
                    title="Odtwarzanie wstrzymane", color=discord.Color.orange())
                await interaction.response.send_message(embed=embed)
            else:
                embed = discord.Embed(
                    title="Błąd", description="Nie odtwarzana jest żadna piosenka.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed)
        except Exception as e:
            print(e)
            embed = discord.Embed(
                title="Błąd", description="Wystąpił błąd podczas wstrzymywania odtwarzania.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)

    @client.tree.command(name="resume", description="Resumes the current song")
    async def resume(interaction: discord.Interaction):
        try:
            if interaction.guild.id in voice_clients and not voice_clients[interaction.guild.id].is_playing():
                voice_clients[interaction.guild.id].resume()
                embed = discord.Embed(
                    title="Odtwarzanie wznowione", color=discord.Color.green())
                await interaction.response.send_message(embed=embed)
            else:
                embed = discord.Embed(
                    title="Błąd", description="Nie ma piosenki do wznowienia.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed)
        except Exception as e:
            print(e)
            embed = discord.Embed(
                title="Błąd", description="Wystąpił błąd podczas wznawiania odtwarzania.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)

    @client.tree.command(name="stop", description="Stops the player")
    async def stop(interaction: discord.Interaction):
        try:
            if interaction.guild.id in voice_clients:
                voice_clients[interaction.guild.id].stop()
                await voice_clients[interaction.guild.id].disconnect()
                del voice_clients[interaction.guild.id]
                embed = discord.Embed(title="Odtwarzanie zatrzymane",
                                      description="Zatrzymano i rozłączono!", color=discord.Color.red())
                await interaction.response.send_message(embed=embed)
            else:
                embed = discord.Embed(
                    title="Błąd", description="Nie ma aktywnego odtwarzacza.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed)
        except Exception as e:
            print(e)
            embed = discord.Embed(
                title="Błąd", description="Wystąpił błąd podczas zatrzymywania.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)

    @client.tree.command(name="queue", description="Displays all enqueued songs")
    async def queue(interaction: discord.Interaction):
        if interaction.guild.id in queues and queues[interaction.guild.id]:
            queue_list = "\n".join(queues[interaction.guild.id])
            embed = discord.Embed(
                title="Obecna kolejka", description=queue_list, color=discord.Color.blue())
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="Kolejka", description="Kolejka jest pusta.", color=discord.Color.yellow())
            await interaction.response.send_message(embed=embed)

    @client.tree.command(name="skip", description="Skips the current song and plays the next in the queue")
    async def skip(interaction: discord.Interaction):
        try:
            if interaction.guild.id in voice_clients and voice_clients[interaction.guild.id].is_playing():
                voice_clients[interaction.guild.id].stop()
                embed = discord.Embed(
                    title="Pominięto", description="Piosenka została pominięta!", color=discord.Color.orange())
                await interaction.response.send_message(embed=embed)
                await play_next(interaction)
            else:
                embed = discord.Embed(
                    title="Błąd", description="Nie odtwarzana jest żadna piosenka.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed)
        except Exception as e:
            print(e)
            embed = discord.Embed(
                title="Błąd", description="Wystąpił błąd podczas pomijania piosenki.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)

    client.run(TOKEN)
