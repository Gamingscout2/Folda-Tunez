"""
Folda Tunez Discord Bot
by Preston Parsons
01/07/2025
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

# Per-guild queue and state management
guild_states = defaultdict(lambda: {
    'queue': Queue(),
    'loop_type': None,  # 'queue', 'song', or None
    'current_song': None,  # Track the current song
})

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.voice_states = True
intents.guild_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

# Customized help command
@bot.command()
async def help_me(ctx):
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

Please Note:
- Playback will take a few seconds to begin!
- Large playlists will take longer to load since audio is downloaded in real-time.

Example Usage:  
- `!play song.mp3` to play a file.
- `!stream <YouTube URL>` to stream audio.

**Folda Tunez version 1.5.1 by Preston Parsons**
[Contact](https://sirobivan.org/index.html)
    """
    await ctx.send(help_text)


# Play the next song in the guild's queue


# Play the next song in the guild's queue
async def play_next(ctx):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]
    queue = state['queue']
    loop_type = state['loop_type']
    current_song = state['current_song']
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if loop_type == 'song' and current_song:
        # Replay the current song
        song = current_song
    else:
        if queue.empty():
            if loop_type == 'queue':
                # Refill the queue if looping the queue
                history = getattr(state, 'history', [])
                for song in history:
                    await queue.put(song)
            else:
                # End playback if no looping
                await ctx.send("The playlist has finished!")
                return
        song = await queue.get()

    state['current_song'] = song  # Update the current song

    if voice_client and not voice_client.is_playing():
        source = discord.FFmpegPCMAudio(song['url'], executable="C:/ffmpeg/bin/ffmpeg.exe")
        voice_client.play(
            source,
            after=lambda e: bot.loop.call_soon_threadsafe(asyncio.create_task, play_next(ctx)) if not e else None
        )
        await ctx.send(f"Now playing: {song['title']}")


@bot.event
async def on_voice_state_update(member, before, after):
    global join_channel
    if (join_channel != None):
        # If the join_channel global variable is
        # not a None type, then the message can be sent in
        # the channel stored in join_channel
        # Check if the bot itself is joining a channel
        if member == bot.user and before.channel is None and after.channel is not None:
            # The bot has joined a voice channel
            channel = join_channel
            await channel.send("Use !help_me for help")
    else:
        # Check if the bot itself is joining a channel
        if member == bot.user and before.channel is None and after.channel is not None:
            # The bot has joined a voice channel
            channel = after.channel
            await channel.send("Use !help_me for help")


# Joins Server message
@bot.event
async def on_guild_join(guild):
    # Get the first available text channel in the guild
    channel = None
    for c in guild.text_channels:
        if c.permissions_for(guild.me).send_messages:
            channel = c
            break

    # Send a message with the help command
    if channel:
        await channel.send("Hello! I'm here to fill your ears with sound! .")
        await channel.send("You can view my commands by typing `!help_me`")


# Join a voice channel
@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"Joined {channel}!")
    else:
        await ctx.send("You need to be in a voice channel for me to join!")


@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.")
    else:
        await ctx.send("I'm not connected to any voice channel!")


@bot.command()
async def play(ctx, *, file_path):
    if not ctx.voice_client:
        await ctx.send("I need to be in a voice channel to play audio! Use !join first.")
        return

    if not os.path.exists(file_path):
        await ctx.send("File not found!")
        return

    ctx.voice_client.stop()  # Stop any currently playing audio
    source = discord.FFmpegPCMAudio(file_path)
    ctx.voice_client.play(source, after=lambda e: print(f'Player error: {e}') if e else None)
    await ctx.send(f"Now playing: {file_path}")


@bot.command()
async def stream(ctx, url):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]
    queue = state['queue']
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client:
        await ctx.send("The bot is not connected to a voice channel.")
        return

    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': False,  # Allow playlists
    }

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if 'entries' in info:
                # Playlist - Add each video to the queue
                for entry in info['entries']:
                    song = {
                        'title': entry['title'],
                        'url': entry['url'],
                    }
                    await queue.put(song)

                if not voice_client.is_playing():
                    await play_next(ctx)
                else:
                    await ctx.send("Added playlist to the queue.")
            else:
                # Single video - Play it immediately
                song = {
                    'title': info['title'],
                    'url': info['url'],
                }
                await queue.put(song)

                if not voice_client.is_playing():
                    await play_next(ctx)
                else:
                    await ctx.send("Added to queue. The bot is already playing.")

    except youtube_dl.utils.DownloadError as e:
        await ctx.send(f"An error occurred while processing the URL: {e}")


@bot.command()
async def skip(ctx):
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
        await queue.put(current_song)  # Add current song back to the queue

    voice_client.stop()
    await ctx.send("Skipping the current track...")


@bot.command()
async def loop(ctx):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]
    loop_type = state['loop_type']

    if loop_type is None:
        state['loop_type'] = 'queue'
        await ctx.send("Looping the entire queue.")
    elif loop_type == 'queue':
        state['loop_type'] = 'song'
        await ctx.send("Looping the current song.")
    elif loop_type == 'song':
        state['loop_type'] = None
        await ctx.send("Looping disabled.")


@bot.command()
async def stop(ctx):
    guild_id = ctx.guild.id
    guild_queue = guild_states[guild_id]['queue']
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if voice_client and voice_client.is_playing():
        # Stop audio playback
        voice_client.stop()

        # Clear the guild queue
        while not guild_queue.empty():
            guild_queue.get_nowait()

        # Reset loop state
        guild_states[guild_id]['loop_type'] = None
        guild_states[guild_id]['current_song'] = None

        await ctx.send("Playback stopped, and the queue has been cleared.")
    else:
        await ctx.send("There is no active playback to stop.")


@bot.command()
async def pause(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client or not voice_client.is_playing():
        await ctx.send("No audio is currently playing to pause.")
        return

    voice_client.pause()
    await ctx.send("Audio playback has been paused.")


@bot.command()
async def resume(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client or not voice_client.is_paused():
        await ctx.send("There is no paused audio to resume.")
        return

    voice_client.resume()
    await ctx.send("Audio playback has been resumed.")

# Replace 'your-token-here' with your actual bot token
bot.run('YOUR-TOKEN-HERE')
