import asyncio
import io
import json as _json
import logging
import os
import aiohttp
import fal_client
from typing import Optional

logger = logging.getLogger(__name__)

FAL_API_KEY    = os.getenv("FAL_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FAL_RUN_URL    = "https://fal.run"

# ── Image models ──────────────────────────────────────────────────────────────
IMAGE_MODEL_NANO   = "fal-ai/nano-banana-2"
IMAGE_MODEL_DALLE  = "dall-e-3"            # via openai SDK
IMAGE_MODEL_GROK   = "xai/grok-imagine-image"

# ── Image edit models ─────────────────────────────────────────────────────────
EDIT_MODEL_NANO    = "fal-ai/nano-banana-pro/edit"
EDIT_MODEL_DALLE   = "dall-e-2"            # only dalle-2 supports edit
EDIT_MODEL_GROK    = "xai/grok-imagine-edit"

# ── Video models (all support audio) ─────────────────────────────────────────
VIDEO_MODEL_MINIMAX = "fal-ai/minimax/video-01-live"
VIDEO_MODEL_VEO     = "fal-ai/veo3"
VIDEO_MODEL_KLING   = "fal-ai/kling-video/v3/pro/text-to-video"
VIDEO_MODEL_GROK    = VIDEO_MODEL_MINIMAX   # legacy alias

# ── Image-to-video models ─────────────────────────────────────────────────────
IMG2VIDEO_MODEL_MINIMAX = "fal-ai/minimax/video-01-live"
IMG2VIDEO_MODEL_GROK    = IMG2VIDEO_MODEL_MINIMAX   # legacy alias
IMG2VIDEO_MODEL_VEO     = "fal-ai/veo3"
IMG2VIDEO_MODEL_KLING   = "fal-ai/kling-video/v3/pro/image-to-video"

# ── Legacy ─────────────────────────────────────────────────────────────────────
IMAGE_MODEL     = "fal-ai/flux/schnell"
VIDEO_MODEL     = "fal-ai/kling-video/v1/standard/text-to-video"
IMG2VIDEO_MODEL = "fal-ai/kling-video/v3/pro/image-to-video"
VID2VID_MODEL   = "fal-ai/video-to-video"

VIDEO_ASPECT_MAP = {
    "16_9": "16:9",
    "9_16": "9:16",
    "1_1":  "1:1",
}

SIZE_MAP = {
    "1_1":  "square_hd",
    "16_9": "landscape_16_9",
    "9_16": "portrait_16_9",
}

# Set fal_client key from env
os.environ.setdefault("FAL_KEY", FAL_API_KEY)


def _headers() -> dict:
    return {
        "Authorization": f"Key {FAL_API_KEY}",
        "Content-Type": "application/json",
    }


def _extract_image_url(result: dict) -> Optional[str]:
    images = result.get("images") or []
    if images:
        first = images[0]
        return first.get("url") if isinstance(first, dict) else first
    return result.get("url") or result.get("image_url")


def _extract_video_url(result: dict) -> Optional[str]:
    video = result.get("video")
    if isinstance(video, dict):
        url = video.get("url")
        if url:
            return url
    if isinstance(video, str) and video.startswith("http"):
        return video
    url = result.get("url") or result.get("video_url")
    if url:
        return url
    output = result.get("output") or {}
    if isinstance(output, dict):
        vid = output.get("video")
        if isinstance(vid, dict):
            return vid.get("url")
        if isinstance(vid, str) and vid.startswith("http"):
            return vid
        return output.get("url") or output.get("video_url")
    logger.error(f"No video URL. Keys: {list(result.keys())} | {str(result)[:400]}")
    return None


# ── Upload helper ──────────────────────────────────────────────────────────────

async def upload_telegram_file(file_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Upload bytes to fal.ai storage and return public URL."""
    if not FAL_API_KEY:
        raise RuntimeError("FAL_API_KEY not configured")
    logger.info(f"Uploading file ({len(file_bytes)} bytes, {mime_type}) to fal.ai")
    url = await fal_client.upload_async(file_bytes, mime_type)
    if not url:
        raise RuntimeError("fal_client.upload_async returned empty URL")
    logger.info(f"Upload done: {url}")
    return url


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE GENERATION
# ══════════════════════════════════════════════════════════════════════════════

_NO_TEXT_SUFFIX = ", no text, no words, no letters, no labels, no watermarks, no captions"


def _ensure_no_text(prompt: str) -> str:
    """Append no-text instruction to every image prompt to prevent text rendering in images."""
    return prompt.rstrip() + _NO_TEXT_SUFFIX


async def generate_infographic_ideogram(topic: str, section_title: str) -> Optional[bytes]:
    """Generate an infographic image via Ideogram v2 and return raw bytes."""
    if not FAL_API_KEY:
        logger.warning("FAL_API_KEY not set; skipping infographic")
        return None
    prompt = (
        f"Clean professional infographic about '{section_title}' related to '{topic}'. "
        "Minimalist design, icons, data visualization, pastel colors, no watermark, no text overlay."
    )
    payload = {
        "prompt": prompt,
        "aspect_ratio": "ASPECT_16_9",
        "model": "V_2",
        "magic_prompt_option": "AUTO",
    }
    try:
        logger.info(f"Ideogram v2: generating infographic for '{section_title}'")
        result = await fal_client.run_async("fal-ai/ideogram/v2", arguments=payload)
        img_url = _extract_image_url(result)
        if not img_url:
            logger.warning(f"Ideogram returned no image URL. Keys: {list(result.keys())}")
            return None
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    return await resp.read()
                logger.warning(f"Failed to download Ideogram image: HTTP {resp.status}")
                return None
    except Exception as e:
        logger.error(f"Ideogram infographic error: {e}")
        return None


async def generate_image_nano(prompt: str, aspect_ratio: str = "1_1") -> str:
    """Generate image via Nano Banana 2 (Google). Returns URL."""
    if not FAL_API_KEY:
        raise RuntimeError("FAL_API_KEY not configured")
    size = SIZE_MAP.get(aspect_ratio, "square_hd")
    payload = {
        "prompt": _ensure_no_text(prompt),
        "image_size": size,
        "num_images": 1,
    }
    logger.info(f"Nano Banana: generating image size={size}")
    result = await fal_client.run_async(IMAGE_MODEL_NANO, arguments=payload)
    url = _extract_image_url(result)
    if not url:
        raise RuntimeError(f"No image URL from Nano Banana. Keys: {list(result.keys())}")
    return url


async def generate_image_dalle(prompt: str, aspect_ratio: str = "1_1") -> str:
    """Generate image via DALL-E 3 (OpenAI). Returns URL."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured. Admin must add this key.")
    from openai import AsyncOpenAI
    size_map = {"1_1": "1024x1024", "16_9": "1792x1024", "9_16": "1024x1792"}
    size = size_map.get(aspect_ratio, "1024x1024")
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    logger.info(f"DALL-E 3: generating image size={size}")
    resp = await client.images.generate(
        model="dall-e-3",
        prompt=_ensure_no_text(prompt),
        n=1,
        size=size,
        quality="standard",
        response_format="url",
    )
    return resp.data[0].url


async def generate_image_grok(prompt: str, aspect_ratio: str = "1_1") -> str:
    """Generate image via Grok Aurora (xAI). Returns URL."""
    if not FAL_API_KEY:
        raise RuntimeError("FAL_API_KEY not configured")
    ar_map = {"1_1": "1:1", "16_9": "16:9", "9_16": "9:16"}
    payload = {
        "prompt": _ensure_no_text(prompt),
        "aspect_ratio": ar_map.get(aspect_ratio, "1:1"),
        "num_images": 1,
    }
    logger.info(f"Grok Aurora: generating image aspect={aspect_ratio}")
    result = await fal_client.run_async(IMAGE_MODEL_GROK, arguments=payload)
    url = _extract_image_url(result)
    if not url:
        raise RuntimeError(f"No image URL from Grok Aurora. Keys: {list(result.keys())}")
    return url


# ── Unified image generate dispatcher ────────────────────────────────────────

async def generate_image_by_model(model: str, prompt: str, aspect_ratio: str = "1_1") -> str:
    if model == "nano":
        return await generate_image_nano(prompt, aspect_ratio)
    elif model == "dalle":
        return await generate_image_dalle(prompt, aspect_ratio)
    elif model == "grok":
        return await generate_image_grok(prompt, aspect_ratio)
    else:
        raise ValueError(f"Unknown image model: {model}")


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE EDITING
# ══════════════════════════════════════════════════════════════════════════════

async def edit_image_nano(image_url: str, prompt: str) -> str:
    """Edit image via Nano Banana Pro. Returns URL."""
    if not FAL_API_KEY:
        raise RuntimeError("FAL_API_KEY not configured")
    payload = {
        "image_urls": [image_url],   # API expects a list
        "prompt": prompt,
    }
    logger.info("Nano Banana: editing image")
    result = await fal_client.run_async(EDIT_MODEL_NANO, arguments=payload)
    url = _extract_image_url(result)
    if not url:
        raise RuntimeError(f"No image URL from Nano Banana edit. Keys: {list(result.keys())}")
    return url


async def edit_image_dalle(image_bytes: bytes, prompt: str) -> str:
    """Edit image via DALL-E 2 inpainting. Returns URL."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured. Admin must add this key.")
    from openai import AsyncOpenAI
    from PIL import Image as PilImage

    # Convert image to square RGBA PNG (DALL-E 2 requirement)
    img = PilImage.open(io.BytesIO(image_bytes))
    side = min(img.size)
    img = img.crop(((img.width - side) // 2, (img.height - side) // 2,
                    (img.width + side) // 2, (img.height + side) // 2))
    img = img.resize((1024, 1024))
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    logger.info("DALL-E 2: editing image")
    resp = await client.images.edit(
        model="dall-e-2",
        image=buf,
        prompt=prompt,
        n=1,
        size="1024x1024",
        response_format="url",
    )
    return resp.data[0].url


async def edit_image_flux(image_url: str, prompt: str) -> str:
    """Edit image via FLUX Dev image-to-image. Returns URL."""
    if not FAL_API_KEY:
        raise RuntimeError("FAL_API_KEY not configured")
    payload = {
        "image_url": image_url,
        "prompt": prompt,
        "strength": 0.75,
        "num_inference_steps": 28,
    }
    logger.info("FLUX Dev: editing image")
    result = await fal_client.run_async("fal-ai/flux/dev/image-to-image", arguments=payload)
    url = _extract_image_url(result)
    if not url:
        raise RuntimeError(f"No image URL from FLUX Dev edit. Keys: {list(result.keys())}")
    return url


# ── Unified image edit dispatcher ────────────────────────────────────────────

async def edit_image_by_model(model: str, image_url: str, image_bytes: bytes, prompt: str) -> str:
    if model == "nano":
        return await edit_image_nano(image_url, prompt)
    elif model == "dalle":
        return await edit_image_dalle(image_bytes, prompt)
    elif model == "grok":
        return await edit_image_flux(image_url, prompt)
    else:
        raise ValueError(f"Unknown edit model: {model}")


# ══════════════════════════════════════════════════════════════════════════════
# VIDEO GENERATION (all with audio)
# ══════════════════════════════════════════════════════════════════════════════

async def generate_video_grok(prompt: str, duration: str = "5", aspect_ratio: str = "16_9") -> str:
    """Generate video via MiniMax Hailuo (video-01-live). Native audio. Returns URL."""
    if not FAL_API_KEY:
        raise RuntimeError("FAL_API_KEY not configured")
    ar = VIDEO_ASPECT_MAP.get(aspect_ratio, "16:9")
    payload = {
        "prompt": prompt,
        "aspect_ratio": ar,
        "prompt_optimizer": True,
    }
    logger.info(f"MiniMax Hailuo: generating {ar}")
    result = await fal_client.run_async(VIDEO_MODEL_MINIMAX, arguments=payload)
    url = _extract_video_url(result)
    if not url:
        raise RuntimeError(f"No video URL from MiniMax. Keys: {list(result.keys())}")
    logger.info(f"MiniMax Hailuo done: {url}")
    return url


async def generate_video_veo(prompt: str, duration: str = "5", aspect_ratio: str = "16_9") -> str:
    """Generate video via Google Veo 3.1 (native audio). Returns URL."""
    if not FAL_API_KEY:
        raise RuntimeError("FAL_API_KEY not configured")
    ar = VIDEO_ASPECT_MAP.get(aspect_ratio, "16:9")
    payload = {
        "prompt": prompt,
        "aspect_ratio": ar,
        "generate_audio": True,
    }
    logger.info(f"Veo 3.1: generating {duration}s {ar}")
    result = await fal_client.run_async(VIDEO_MODEL_VEO, arguments=payload)
    url = _extract_video_url(result)
    if not url:
        raise RuntimeError(f"No video URL from Veo 3.1. Keys: {list(result.keys())}")
    logger.info(f"Veo 3.1 done: {url}")
    return url


async def generate_video_kling(prompt: str, duration: str = "5", aspect_ratio: str = "16_9") -> str:
    """Generate video via Kling v3 Pro (native audio). Returns URL."""
    if not FAL_API_KEY:
        raise RuntimeError("FAL_API_KEY not configured")
    ar = VIDEO_ASPECT_MAP.get(aspect_ratio, "16:9")
    payload = {
        "prompt": prompt,
        "duration": duration,
        "aspect_ratio": ar,
        "generate_audio": True,
    }
    logger.info(f"Kling v3 Pro: generating {duration}s {ar}")
    result = await fal_client.run_async(VIDEO_MODEL_KLING, arguments=payload)
    url = _extract_video_url(result)
    if not url:
        raise RuntimeError(f"No video URL from Kling v3 Pro. Keys: {list(result.keys())}")
    logger.info(f"Kling v3 Pro done: {url}")
    return url


# ── Unified video generate dispatcher ────────────────────────────────────────

async def generate_video_by_model(
    model: str, prompt: str, duration: str = "5", aspect_ratio: str = "16_9"
) -> str:
    if model == "grok":
        return await generate_video_grok(prompt, duration, aspect_ratio)
    elif model == "veo":
        return await generate_video_veo(prompt, duration, aspect_ratio)
    elif model == "kling":
        return await generate_video_kling(prompt, duration, aspect_ratio)
    else:
        raise ValueError(f"Unknown video model: {model}")


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE → VIDEO
# ══════════════════════════════════════════════════════════════════════════════

async def image_to_video_grok(image_url: str, prompt: str = "") -> str:
    """Image to video via MiniMax Hailuo. Uses first_frame_image."""
    payload = {
        "first_frame_image": image_url,
        "prompt": prompt or "animate this image naturally",
        "prompt_optimizer": True,
    }
    logger.info("MiniMax Hailuo: image to video")
    result = await fal_client.run_async(IMG2VIDEO_MODEL_MINIMAX, arguments=payload)
    url = _extract_video_url(result)
    if not url:
        raise RuntimeError(f"No URL from MiniMax img2video. Keys: {list(result.keys())}")
    return url


async def image_to_video_veo(image_url: str, prompt: str = "") -> str:
    payload = {
        "image_url": image_url,
        "prompt": prompt or "animate this image naturally",
        "generate_audio": True,
    }
    logger.info("Veo 3.1: image to video")
    result = await fal_client.run_async(IMG2VIDEO_MODEL_VEO, arguments=payload)
    url = _extract_video_url(result)
    if not url:
        raise RuntimeError(f"No URL from Veo img2video. Keys: {list(result.keys())}")
    return url


async def image_to_video_kling(image_url: str, prompt: str = "") -> str:
    payload = {
        "image_url": image_url,
        "prompt": prompt or "animate this image naturally",
        "generate_audio": True,
    }
    logger.info("Kling v3 Pro: image to video")
    result = await fal_client.run_async(IMG2VIDEO_MODEL_KLING, arguments=payload)
    url = _extract_video_url(result)
    if not url:
        raise RuntimeError(f"No URL from Kling img2video. Keys: {list(result.keys())}")
    return url


async def image_to_video_by_model(model: str, image_url: str, prompt: str = "") -> str:
    if model == "grok":
        return await image_to_video_grok(image_url, prompt)
    elif model == "veo":
        return await image_to_video_veo(image_url, prompt)
    elif model == "kling":
        return await image_to_video_kling(image_url, prompt)
    else:
        raise ValueError(f"Unknown img2video model: {model}")


# ══════════════════════════════════════════════════════════════════════════════
# LEGACY (used by old flow, kept for compat)
# ══════════════════════════════════════════════════════════════════════════════

async def generate_image(prompt: str, size: str = "1024x1024", aspect_ratio: str = "1_1") -> Optional[str]:
    return await generate_image_nano(prompt, aspect_ratio)


async def generate_video(prompt: str, duration: str = "5", aspect_ratio: str = "16_9") -> Optional[str]:
    return await generate_video_kling(prompt, duration, aspect_ratio)


async def image_to_video(image_url: str, prompt: str = "") -> Optional[str]:
    return await image_to_video_kling(image_url, prompt)


async def video_to_video(video_url: str, prompt: str) -> Optional[str]:
    raise RuntimeError("Video-to-video feature has been removed")
