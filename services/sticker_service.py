import io
import os
import asyncio
import logging
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

logger = logging.getLogger(__name__)

STICKER_SIZE = 512
_executor = ThreadPoolExecutor(max_workers=4)


def _convert_to_webp_sticker(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size
    if w >= h:
        new_w = STICKER_SIZE
        new_h = max(1, int(h * STICKER_SIZE / w))
    else:
        new_h = STICKER_SIZE
        new_w = max(1, int(w * STICKER_SIZE / h))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=90, method=6)
    return buf.getvalue()


def _convert_video_to_webm_sticker(video_bytes: bytes) -> bytes:
    """
    Convert video to a Telegram-compatible video sticker:
    WebM (VP9), 512x512, max 3 seconds, 30fps, no audio.
    """
    tmp_in = None
    tmp_out = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            tmp_in = f.name

        tmp_out = tmp_in.replace(".mp4", "_sticker.webm")

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", tmp_in,
                "-t", "3",
                "-vf",
                "scale=512:512:force_original_aspect_ratio=decrease,"
                "pad=512:512:(ow-iw)/2:(oh-ih)/2:color=black,"
                "fps=30",
                "-c:v", "libvpx-vp9",
                "-b:v", "300k",
                "-crf", "33",
                "-deadline", "realtime",
                "-cpu-used", "4",
                "-an",
                tmp_out,
            ],
            capture_output=True,
            timeout=60,
        )

        if result.returncode != 0:
            err = result.stderr.decode(errors="replace")
            logger.error(f"ffmpeg error: {err}")
            raise RuntimeError(f"ffmpeg failed: {err[:300]}")

        with open(tmp_out, "rb") as f:
            data = f.read()

        if len(data) == 0:
            raise RuntimeError("ffmpeg produced empty output file")

        return data

    finally:
        if tmp_in and os.path.exists(tmp_in):
            os.unlink(tmp_in)
        if tmp_out and os.path.exists(tmp_out):
            os.unlink(tmp_out)


async def image_to_webp_sticker(image_bytes: bytes) -> bytes:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _convert_to_webp_sticker, image_bytes)


async def video_to_webm_sticker(video_bytes: bytes) -> bytes:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _convert_video_to_webm_sticker, video_bytes
    )
