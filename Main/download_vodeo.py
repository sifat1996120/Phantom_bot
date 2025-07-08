import subprocess
import asyncio
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes, 


async def download_video(update : Update, content : ContextTypes, channel_id, user_id, url, quality) -> None:
    
    quality_format = {
        "1080p" : "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p" : "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "1080p" : "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "1080p" : "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "audio" : "bestaudio"
    }

    message = await update.message.reply_text("Preparing your download...")

    format_string = quality_format.get(quality, quality_format["720p"])

    command = [
        "yt-dlp",
        "--max-filesize", '500M',
        "-f", format_string,
        "-o", "-",
        url
    ]

    buffer = BytesIO()
    buffer.name = "video.mp4"

    try:
        process = await asyncio.create_subprocess_exe(
            *command,
            stdout = asyncio.subprocess.PIPE,
            stderr = asyncio.subprocess.PIPE
        )

        downloaded = 0
        last_update = 0
        
        while True:
            chunk = await process.stdout.read(1024*512)
            if not chunk:
                break
            buffer.write(chunk)
            downloaded += len(chunk)

            now = asyncio.get_event_loop().time()
            if now - last_update > 1:
                mb = downloaded/(1024*10242)
                await message.edit_text(f"Downloaded: {mb:.2f} MB")
                last_update = now
        await process.wait()