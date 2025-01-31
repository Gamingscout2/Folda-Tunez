"""
Folda Tunez Discord Bot
by Preston Parsons
01/07/2025

Version 1.6 updated 01/30/2025
Changes:
    Per-Server queueing improved

    YouTube playback updated to working state

    Audio Extraction Updates:

        Added extract_audio and postprocessors to ydl_opts to ensure audio is extracted directly.

        Prefers mp3 format with a quality of 192kbps.

    Error Handling:

        Improved error handling for YouTube URL processing.

    Playlist Support:

        Handles playlists more efficiently by extracting all entries.

    Logging:

        Added logging to help debug issues.


Version 1.5.1 updated 01/08/2025
Changes:
    Support for per-server (guild) queue and playback,
    fixing the issue where playback was shared globally
    across multiple servers

    Stop function fixed

    Skip function fixed, if a loop is enabled it will retain the queue

    Looping updated to allow looping of the current track
    Three Loop States:
        None: No looping.
        'queue': Loop the entire queue.
        'song': Loop the currently playing song.
    Queue Refill for Looping:
        If the queue is empty and the loop type is 'queue', the bot refills the queue with previously played songs.
    Replay Current Song for 'song' Looping:
        The current_song is stored in guild_states to replay the current track if looping the song.
    Cycle Through States:
        The !loop command cycles through the three states.

Version 1.5 updated 01/07/2025
Features:
Join a voice channel
Play audio from a path on your local machine
Stream audio from link (only DRM free links will work, no spotify as of 1.5)
Full queue support and YouTube playlist support, including:
    Skip current track
    Pause/Resume Playback
    Loop entire queue
    Loop current song coming in next update

Subject to the license terms found at: https://sirobivan.org/pcl1-1.html
Copyright 2025 Parsons Computing
"""

import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import os
import asyncio
from asyncio import Queue
from collections import defaultdict
import random
import platform
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# Per-guild queue and state management
guild_states = defaultdict(lambda: {
    'queue': Queue(),
    'loop_type': None,  # 'queue', 'song', or None
    'current_song': None,  # Track the current song
    'history': [],  # Track history for queue looping
})

# Determine FFmpeg path based on the operating system
ffmpeg_path = "ffmpeg"  # Default to assuming ffmpeg is in the PATH
if platform.system() == "Windows":
    ffmpeg_path = "C:/ffmpeg/bin/ffmpeg.exe"

# Set up intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.voice_states = True
intents.guild_messages = True

join_channel = None
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    """Event triggered when the bot is ready and logged in."""
    print(f'Logged in as {bot.user}')

@bot.command()
async def help_me(ctx):
    """
    Displays a help message with a list of available commands.

    Args:
        ctx (commands.Context): The context of the command invocation.
    """
    help_text = """
**Bot Commands List**:

**!join** - Makes the bot join your current voice channel.
**!leave** - Makes the bot leave the voice channel.
**!play <file_path>** - Play an MP3 file from a local path.
**!stream <URL>** - Stream audio from a YouTube URL.
**!skip** - Skip the current track and play the next one in the queue.
**!stop** - Stop the current audio playback.
**!loop** - Toggle between three loop modes:
  1. Loop the entire queue.
  2. Loop the current song.
  3. Disable looping.
**!pause** - Pause the current audio playback.
**!resume** - Resume the paused audio playback.
**!shuffle** - Shuffles the queue.
**!playlist_local** - Takes a file path to a .txt file holding file paths to
                      mp3 files on the users PC (only works from host of bot for now)

Please Note:
- Playback will take a few seconds to begin!
- Large playlists will take longer to load since audio is downloaded in real-time.

Example Usage:  
- `!play song.mp3` to play a file.
- `!stream <YouTube URL>` to stream audio.

**Folda Tunez version 1.6 by Preston Parsons**
[Contact](https://sirobivan.org/index.html)
    """
    await ctx.send(help_text)

async def play_next(ctx):
    """
    Plays the next song in the guild's queue.

    Args:
        ctx (commands.Context): The context of the command invocation.
    """
    guild_id = ctx.guild.id
    state = guild_states[guild_id]
    queue = state['queue']
    loop_type = state['loop_type']
    current_song = state['current_song']
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    try:
        if loop_type == 'song' and current_song:
            song = current_song
        elif not queue.empty():
            song = await queue.get()
        elif loop_type == 'queue' and state.get('history', []):
            for track in state['history']:
                await queue.put(track)
            song = await queue.get()
        else:
            state['current_song'] = None
            await ctx.send("The playlist has finished!")
            return

        state['current_song'] = song
        state['history'].append(song)

        if voice_client and not voice_client.is_playing():
            source = discord.FFmpegPCMAudio(
                song['url'],
                executable=ffmpeg_path,
                options="-buffer_size 16M"
            )
            voice_client.play(
                source,
                after=lambda e: bot.loop.call_soon_threadsafe(
                    asyncio.create_task, play_next(ctx)
                ) if e is None else print(f"Error: {e}")
            )
            await ctx.send(f"Now playing: {song['title']}")
    except Exception as e:
        logging.error(f"Error in play_next: {e}")
        await ctx.send("An error occurred while trying to play the next song.")

@bot.event
async def on_voice_state_update(member, before, after):
    """
    Event triggered when a user's voice state changes (e.g., joins/leaves a voice channel).

    Args:
        member (discord.Member): The member whose voice state changed.
        before (discord.VoiceState): The previous voice state.
        after (discord.VoiceState): The new voice state.
    """
    global join_channel
    if join_channel is not None:
        if member == bot.user and before.channel is None and after.channel is not None:
            channel = join_channel
            await channel.send("Use !help_me for help")
    else:
        if member == bot.user and before.channel is None and after.channel is not None:
            channel = after.channel
            await channel.send("Use !help_me for help")

@bot.event
async def on_guild_join(guild):
    """
    Event triggered when the bot joins a new guild.

    Args:
        guild (discord.Guild): The guild the bot joined.
    """
    channel = None
    for c in guild.text_channels:
        if c.permissions_for(guild.me).send_messages:
            channel = c
            break

    if channel:
        await channel.send("Hello! I'm here to fill your ears with sound! .")
        await channel.send("You can view my commands by typing `!help_me`")

@bot.command()
async def join(ctx):
    """
    Makes the bot join the user's current voice channel.

    Args:
        ctx (commands.Context): The context of the command invocation.
    """
    global join_channel
    if ctx.author.voice:
        join_channel = ctx.author.voice.channel
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"Joined {channel}!")
    else:
        await ctx.send("You need to be in a voice channel for me to join!")

@bot.command()
async def leave(ctx):
    """
    Makes the bot leave the current voice channel.

    Args:
        ctx (commands.Context): The context of the command invocation.
    """
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.")
    else:
        await ctx.send("I'm not connected to any voice channel!")

@bot.command()
async def shuffle(ctx):
    """
    Shuffles the current queue for the guild.

    Args:
        ctx (commands.Context): The context of the command invocation.
    """
    guild_id = ctx.guild.id
    state = guild_states[guild_id]
    queue = state['queue']

    items = []
    while not queue.empty():
        items.append(await queue.get())

    if len(items) < 2:
        await ctx.send("Not enough songs in the queue to shuffle.")
        for item in items:
            await queue.put(item)
        return

    random.shuffle(items)

    for item in items:
        await queue.put(item)

@bot.command()
async def play(ctx, *, file_paths: str):
    """
    Plays multiple audio files by adding them to the queue and starting playback.

    Args:
        ctx (commands.Context): The context of the command invocation.
        file_paths (str): A comma-separated list of file paths.
    """
    guild_id = ctx.guild.id
    state = guild_states[guild_id]
    queue = state['queue']

    paths = [path.strip() for path in file_paths.split(",")]
    added_count = 0

    for file_path in paths:
        if os.path.exists(file_path):
            song = {'title': os.path.basename(file_path), 'url': file_path}
            await queue.put(song)
            added_count += 1
        else:
            await ctx.send(f"File not found: {file_path}")

    if added_count > 0:
        await ctx.send(f"Added {added_count} songs to the queue.")

        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if voice_client and not voice_client.is_playing():
            await play_next(ctx)
    else:
        await ctx.send("No valid files were added to the queue.")

@bot.command()
async def stream(ctx, url):
    """
    Streams audio from a YouTube URL and adds it to the queue.

    Args:
        ctx (commands.Context): The context of the command invocation.
        url (str): The YouTube URL to stream.
    """
    guild_id = ctx.guild.id
    state = guild_states[guild_id]
    queue = state['queue']
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client:
        await ctx.send("The bot is not connected to a voice channel.")
        return

    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': False,
        'extract_audio': True,
        'audio_format': 'best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if 'entries' in info:
                for entry in info['entries']:
                    song = {'title': entry['title'], 'url': entry['url']}
                    await queue.put(song)

                await ctx.send("Added playlist to the queue.")
            else:
                song = {'title': info['title'], 'url': info['url']}
                await queue.put(song)
                await ctx.send(f"Added {song['title']} to the queue.")

            if not voice_client.is_playing():
                await play_next(ctx)

    except youtube_dl.utils.DownloadError as e:
        await ctx.send(f"An error occurred while processing the URL: {e}")

@bot.command()
async def skip(ctx):
    """
    Skips the current track and plays the next one in the queue.

    Args:
        ctx (commands.Context): The context of the command invocation.
    """
    guild_id = ctx.guild.id
    state = guild_states[guild_id]
    queue = state['queue']
    loop_type = state['loop_type']
    current_song = state['current_song']
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client or not voice_client.is_playing():
        await ctx.send("No audio is currently playing to skip.")
        return

    if loop_type == 'queue' and current_song:
        await queue.put(current_song)

    voice_client.stop()
    await ctx.send("Skipping the current track...")

@bot.command()
async def loop(ctx):
    """
    Toggles between three loop modes: none, queue, and song.

    Args:
        ctx (commands.Context): The context of the command invocation.
    """
    guild_id = ctx.guild.id
    state = guild_states[guild_id]
    loop_type = state['loop_type']

    if loop_type is None:
        state['loop_type'] = 'queue'
        state['history'] = []
        await ctx.send("Looping the entire queue.")
    elif loop_type == 'queue':
        state['loop_type'] = 'song'
        await ctx.send("Looping the current song.")
    elif loop_type == 'song':
        state['loop_type'] = None
        await ctx.send("Looping disabled.")

@bot.command()
async def stop(ctx):
    """
    Stops the current audio playback and clears the queue.

    Args:
        ctx (commands.Context): The context of the command invocation.
    """
    guild_id = ctx.guild.id
    guild_queue = guild_states[guild_id]['queue']
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if voice_client and voice_client.is_playing():
        voice_client.stop()

        while not guild_queue.empty():
            guild_queue.get_nowait()

        guild_states[guild_id]['loop_type'] = None
        guild_states[guild_id]['current_song'] = None

        await ctx.send("Playback stopped, and the queue has been cleared.")
    else:
        await ctx.send("There is no active playback to stop.")

@bot.command()
async def pause(ctx):
    """
    Pauses the current audio playback.

    Args:
        ctx (commands.Context): The context of the command invocation.
    """
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client or not voice_client.is_playing():
        await ctx.send("No audio is currently playing to pause.")
        return

    voice_client.pause()
    await ctx.send("Audio playback has been paused.")

@bot.command()
async def resume(ctx):
    """
    Resumes the paused audio playback.

    Args:
        ctx (commands.Context): The context of the command invocation.
    """
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client or not voice_client.is_paused():
        await ctx.send("There is no paused audio to resume.")
        return

    voice_client.resume()
    await ctx.send("Audio playback has been resumed.")

@bot.command()
async def playlist_local(ctx, filename: str):
    """
    Loads a playlist from a text file and adds the songs to the queue.

    Args:
        ctx (commands.Context): The context of the command invocation.
        filename (str): The name of the text file containing the playlist.
    """
    guild_id = ctx.guild.id
    state = guild_states[guild_id]
    queue = state['queue']

    filepath = os.path.join(os.getcwd(), filename)

    if not os.path.exists(filepath):
        await ctx.send(f"File '{filename}' not found in the bot's directory.")
        return

    try:
        with open(filepath, 'r') as file:
            songs = [line.strip() for line in file if line.strip()]

        if not songs:
            await ctx.send("The playlist file is empty.")
            return

        for song_path in songs:
            if os.path.exists(song_path):
                await queue.put({'title': os.path.basename(song_path), 'url': song_path})
            else:
                await ctx.send(f"File not found: {song_path}")

        await ctx.send(f"Added {len(songs)} songs to the queue.")

        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if voice_client and not voice_client.is_playing():
            await play_next(ctx)

    except Exception as e:
        await ctx.send(f"An error occurred while loading the playlist: {e}")

# Replace 'your-token-here' with your actual bot token
bot.run(your-token-here)
