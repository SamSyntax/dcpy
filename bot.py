# bot.py

import discord
from discord import app_commands
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import urllib.parse
import urllib.request
import re
import speech_recognition as sr
import io
import wave
import audioop


class MusicBot:
    def __init__(self):
        load_dotenv()
        self.TOKEN = os.getenv('CLIENT_TOKEN')
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)

        self.queues = {}
        self.voice_clients = {}
        self.youtube_base_url = 'https://www.youtube.com/'
        self.youtube_results_url = self.youtube_base_url + 'results?'
        self.youtube_watch_url = self.youtube_base_url + 'watch?v='
        self.yt_dl_options = {"format": "bestaudio/best"}
        self.ytdl = yt_dlp.YoutubeDL(self.yt_dl_options)

        self.ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                               'options': '-vn -filter:a "volume=0.25"'}

        self.recognizer = sr.Recognizer()

        self.setup_events()
        self.setup_commands()

    def setup_events(self):
        @self.client.event
        async def on_ready():
            print(f'{self.client.user} is now jamming')
            await self.tree.sync()
            print("Slash commands synced")

    def setup_commands(self):
        @self.tree.command(name="join", description="Join a voice channel")
        async def join(interaction: discord.Interaction):
            if interaction.user.voice:
                channel = interaction.user.voice.channel
                voice_client = await channel.connect()
                self.voice_clients[interaction.guild.id] = voice_client
                await interaction.response.send_message(f"Joined {channel}")
                text_channel = interaction.channel
                await self.listen_to_channel(voice_client, text_channel)
            else:
                await interaction.response.send_message("You need to be in a voice channel to use this command.")

        @self.tree.command(name="play", description="Play a song from YouTube")
        @app_commands.describe(query="The YouTube URL or search term")
        async def play(interaction: discord.Interaction, query: str):
            await interaction.response.defer()
            await self.play_from_message(interaction, query)

        @self.tree.command(name="skip", description="Skip the current song")
        async def skip(interaction: discord.Interaction):
            try:
                if interaction.guild.id in self.voice_clients:
                    self.voice_clients[interaction.guild.id].stop()
                    await interaction.response.send_message("Skipped the current song.")
                    await self.play_next(interaction.guild)
                else:
                    await interaction.response.send_message("No song is currently playing.")
            except Exception as e:
                print(f"Error in skip command: {e}")
                await interaction.response.send_message("An error occurred while trying to skip.")

        @self.tree.command(name="queue", description="Show the current queue")
        async def show_queue(interaction: discord.Interaction):
            if interaction.guild.id in self.queues and self.queues[interaction.guild.id]:
                queue_list = "\n".join(
                    [f"{i+1}. {song}" for i, song in enumerate(self.queues[interaction.guild.id])])
                await interaction.response.send_message(f"Current queue:\n{queue_list}")
            else:
                await interaction.response.send_message("The queue is empty.")

        @self.tree.command(name="clear_queue", description="Clear the current queue")
        async def clear_queue(interaction: discord.Interaction):
            if interaction.guild.id in self.queues:
                self.queues[interaction.guild.id].clear()
                await interaction.response.send_message("Queue cleared!")
            else:
                await interaction.response.send_message("There is no queue to clear")

        @self.tree.command(name="pause", description="Pause the current song")
        async def pause(interaction: discord.Interaction):
            try:
                self.voice_clients[interaction.guild.id].pause()
                await interaction.response.send_message("Playback paused.")
            except Exception as e:
                print(e)
                await interaction.response.send_message("An error occurred while trying to pause.")

        @self.tree.command(name="resume", description="Resume the paused song")
        async def resume(interaction: discord.Interaction):
            try:
                self.voice_clients[interaction.guild.id].resume()
                await interaction.response.send_message("Playback resumed.")
            except Exception as e:
                print(e)
                await interaction.response.send_message("An error occurred while trying to resume.")

        @self.tree.command(name="stop", description="Stop playback and disconnect the bot")
        async def stop(interaction: discord.Interaction):
            try:
                self.voice_clients[interaction.guild.id].stop()
                await self.voice_clients[interaction.guild.id].disconnect()
                del self.voice_clients[interaction.guild.id]
                if interaction.guild.id in self.queues:
                    self.queues[interaction.guild.id].clear()
                await interaction.response.send_message("Playback stopped and disconnected.")
            except Exception as e:
                print(e)
                await interaction.response.send_message("An error occurred while trying to stop.")

    async def listen_to_channel(self, voice_client, text_channel):
        def callback(sink, audio_data):
            if len(audio_data) == 0:
                return

            print("Received audio data")  # Debug print

            # Convert audio data to wav format
            audio = audioop.ratecv(audio_data, 2, 1, 48000, 16000, None)[0]
            wav_data = io.BytesIO()
            with wave.open(wav_data, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(audio)

            wav_data.seek(0)

            try:
                # Use speech recognition
                with sr.AudioFile(wav_data) as source:
                    audio = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio)
                print(f"Recognized text: {text}")  # Debug print

                if text.lower().startswith("play "):
                    query = text[5:]
                    print(f"Detected play command: {query}")  # Debug print
                    asyncio.create_task(
                        self.play_from_voice(text_channel, query))
                else:
                    print("No play command detected")  # Debug print
            except sr.UnknownValueError:
                # Debug print
                print("Speech recognition could not understand audio")
            except sr.RequestError as e:
                # Debug print
                print(
                    f"Could not request results from speech recognition service; {e}")

        print("Starting voice recognition")  # Debug print
        voice_client.start_recording(
            discord.sinks.WaveSink(), callback, text_channel)

    async def play_from_voice(self, text_channel, query):
        guild = text_channel.guild
        if guild.id not in self.voice_clients:
            await text_channel.send("I'm not in a voice channel. Use the join command first.")
            return

        try:
            url = await asyncio.get_event_loop().run_in_executor(None, self.youtube_search, query)

            if guild.id not in self.queues:
                self.queues[guild.id] = []

            self.queues[guild.id].append(url)

            if not self.voice_clients[guild.id].is_playing():
                await self.play_next(guild)
                await text_channel.send(f"Now playing: {url}")
            else:
                await text_channel.send(f"Added to queue: {url}")
        except Exception as e:
            print(f"Error in play command: {e}")
            await text_channel.send("An error occurred while trying to play the song.")

    async def play_from_message(self, interaction, query):
        if not interaction.user.voice:
            await interaction.followup.send("You need to be in a voice channel to use this command.")
            return

        try:
            if interaction.guild.id not in self.voice_clients:
                voice_client = await interaction.user.voice.channel.connect()
                self.voice_clients[interaction.guild.id] = voice_client

            url = await asyncio.get_event_loop().run_in_executor(None, self.youtube_search, query)

            if interaction.guild.id not in self.queues:
                self.queues[interaction.guild.id] = []

            self.queues[interaction.guild.id].append(url)

            if not self.voice_clients[interaction.guild.id].is_playing():
                await self.play_next(interaction.guild)
                await interaction.followup.send(f"Now playing: {url}")
            else:
                await interaction.followup.send(f"Added to queue: {url}")
        except Exception as e:
            print(f"Error in play command: {e}")
            await interaction.followup.send("An error occurred while trying to play the song.")

    def youtube_search(self, query):
        if self.youtube_base_url not in query:
            query_string = urllib.parse.urlencode({'search_query': query})
            content = urllib.request.urlopen(
                self.youtube_results_url + query_string)
            search_results = re.findall(
                r'/watch\?v=(.{11})', content.read().decode())
            return self.youtube_watch_url + search_results[0]
        return query

    def get_audio_source(self, url):
        info = self.ytdl.extract_info(url, download=False)
        return discord.FFmpegOpusAudio(info['url'], **self.ffmpeg_options)

    async def play_next(self, guild):
        if guild.id in self.queues and self.queues[guild.id]:
            url = self.queues[guild.id].pop(0)
            voice_client = self.voice_clients[guild.id]

            def after_playing(error):
                asyncio.run_coroutine_threadsafe(
                    self.play_next(guild), self.client.loop)

            try:
                audio_source = await asyncio.get_event_loop().run_in_executor(None, self.get_audio_source, url)
                voice_client.play(audio_source, after=after_playing)

                # Send a message to the guild's system channel
                if guild.system_channel:
                    await guild.system_channel.send(f"Now playing: {url}")
            except Exception as e:
                print(f"Error playing next song: {e}")
                if guild.system_channel:
                    await guild.system_channel.send("An error occurred while trying to play the next song.")

    def run(self):
        self.client.run(self.TOKEN)


# Add this line at the end of the file
__all__ = ['MusicBot']
