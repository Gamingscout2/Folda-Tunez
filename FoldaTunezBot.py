"""
Folda Tunez Discord Bot
by Preston Parsons
01/07/2024

Version 1.5 updated 01/07/2024
Features:
Join a voice channel
Play audio from a path on your local machine
Stream audio from link (only DRM free links will work, no spotify as of 1.5)
Full queue support and YouTube playlist support, including:
    Skip current track
    Pause/Resume Playback
    Loop entire queue
    Loop current song coming in 1.6
    
Subject to the license terms found at: https://sirobivan.org/pcl1-1.html
Copyright 2025 Parsons Computing
"""

import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import os
import asyncio
from asyncio import Queue

audio_queue = Queue()
is_looping = False  # Loop state
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.voice_states = True
intents.guild_messages = True
ffmpeg_source = 'C:/ffmpeg-7.0.2/bin/ffmpeg.exe'
join_channel = None
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
**!loop** - Toggle looping of the current playlist.
**!pause** - Pause the current audio playback.
**!resume** - Resume the paused audio playback.

Please Note - playback will take a few seconds to begin!
Large playlists will take even longer, to download youtube audio
it requires a workaround that takes a noticeable amount of time!!
Use `!help_me <command>` for more details on a specific command.

Example: `!help_me play`

**Folda Tunez version 1.5 by Preston Parsons**
    """
    await ctx.send(help_text)


async def play_next(ctx):
    if audio_queue.empty():
        await ctx.send("The playlist has finished!")
        return

    # Get the next song from the queue
    song = await audio_queue.get()
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if voice_client and not voice_client.is_playing():
        source = discord.FFmpegPCMAudio(song['url'], executable="C:/ffmpeg/bin/ffmpeg.exe")

        # Use an async lambda to properly await play_next
        voice_client.play(source, after=lambda e: asyncio.create_task(play_next(ctx)) if not e else None)
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
        await channel.send("Hello! I'm here to help. You can view my commands by typing `!help_me`.")


# Join a voice channel
@bot.command()
async def join(ctx):
    global join_channel
    join_channel = ctx.channel  # Store the text channel where the command was invoked
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await join_channel.send(f"Joined {channel}!")
    else:
        await join_channel.send("You need to be in a voice channel for me to join!")

# Leave a voice channel
@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await join_channel.send("Disconnected from the voice channel.")
    else:
        await ctx.send("I'm not connected to any voice channel!")

# Play an MP3 file from a local path
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

# Skip current song
@bot.command()
async def skip(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client or not voice_client.is_playing():
        await ctx.send("No audio is currently playing.")
        return

    # Stop the current track
    voice_client.stop()
    await ctx.send("Skipping the current track...")

    # Play the next track in the queue
    await play_next(ctx)

# Play audio from a URL
@bot.command()
async def stream(ctx, url):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client:
        await ctx.send("The bot is not connected to a voice channel.")
        return

    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': False,  # Allow playlists
        'extractaudio': True,  # Ensure only audio is extracted
        'forcejson': True,  # Force JSON extraction, which helps with extracting URL
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
                    await audio_queue.put(song)

                if not voice_client.is_playing():
                    await play_next(ctx)  # Start playing the first song in the queue
                else:
                    await ctx.send("Added to queue. The bot is already playing.")
            else:
                # Single video - Play it immediately
                song = {
                    'title': info['title'],
                    'url': info['url'],
                }
                await audio_queue.put(song)

                if not voice_client.is_playing():
                    await play_next(ctx)  # Start playing the single song
                else:
                    await ctx.send("Added to queue. The bot is already playing.")

    except youtube_dl.utils.DownloadError as e:
        await ctx.send(f"An error occurred while processing the URL: {e}")

# Stop playing audio
@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("Playback stopped.")
    else:
        await ctx.send("I'm not playing any audio.")

# Loop command to toggle repeating the queue
@bot.command()
async def loop(ctx):
    global is_looping

    if is_looping:
        is_looping = False
        await ctx.send("Looping has been disabled.")
    else:
        is_looping = True
        await ctx.send("Looping has been enabled. The queue will repeat after it finishes.")
        if audio_queue.empty():
            await ctx.send("No songs in the queue to loop.")

# Pause the current playback
@bot.command()
async def pause(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client or not voice_client.is_playing():
        await ctx.send("No audio is currently playing to pause.")
        return

    voice_client.pause()
    await ctx.send("Audio playback has been paused.")

# Resume the paused playback
@bot.command()
async def resume(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client or not voice_client.is_paused():
        await ctx.send("There is no paused audio to resume.")
        return

    voice_client.resume()
    await ctx.send("Audio playback has been resumed.")

# Replace 'your-token-here' with your actual bot token
bot.run('TOKEN GOES HERE')
