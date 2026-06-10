import io
import asyncio
import logging
from typing import Literal

import numpy as np
import soundfile as sf
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from ..backend import generate
from ..config import TTS_CONCURRENCY_LIMIT
from ..utils import SPEED_MAP, VOLUME_MAP, audio_bytes_to_wav_bytes
from .common import (
    TTS_STYLE,
    get_prompt_paths,
    load_profile,
    check_audio_bytes,
)


router = APIRouter(tags=["tts"])
logger = logging.getLogger(__name__)
tts_semaphore = asyncio.Semaphore(max(1, TTS_CONCURRENCY_LIMIT))

OutputFormat = Literal["pcm", "mp3", "wav", "aac", "m4a", "opus", "ogg", "flac", "webm"]

MEDIA_TYPES = {
    "pcm": "application/octet-stream",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "aac": "audio/aac",
    "m4a": "audio/mp4",
    "opus": "audio/ogg",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
    "webm": "audio/webm",
}


def volume_to_linear(volume: str) -> float:
    return VOLUME_MAP[volume]


def audio_response(audio_bytes: bytes, output_format: OutputFormat) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type=MEDIA_TYPES[output_format],
        headers={"Content-Disposition": f'inline; filename="tts.{output_format}"'},
    )


async def process(
    text: str,
    userId: str,
    speakerId: str,
    speed: Literal["low", "balanced", "fast"] = "balanced",
    volume: Literal["small", "middle", "large"] = "middle",
    output_format: OutputFormat = "mp3",
    max_chars: int = 80,
):
    text = text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")
    if max_chars <= 0:
        raise HTTPException(status_code=400, detail="max_chars 必须大于 0")

    audio_path, profile_path, _ = get_prompt_paths(userId, speakerId, check_exists=True)

    waveform, sr = sf.read(audio_path)
    assert sr == 16000, "sample rate hardcoded in server"

    samples = np.array(waveform, dtype=np.float32)

    profile = load_profile(profile_path)
    audio_text = profile.get("text", "").strip()

    if not audio_text:
        raise HTTPException(status_code=400, detail="speaker profile.text 不能为空")

    logger.info(
        "tts requested userId=%s speakerId=%s text_chars=%s output_format=%s speed=%s volume=%s",
        userId,
        speakerId,
        len(text),
        output_format,
        speed,
        volume,
    )

    async with tts_semaphore:
        audio_bytes = await asyncio.to_thread(
            generate,
            reference_audio=samples,
            reference_text=audio_text,
            target_text=text,
            max_chars=max_chars,
            output_format=output_format,
            volume=volume_to_linear(volume),
            speed=SPEED_MAP[speed],
        )

    if not isinstance(audio_bytes, (bytes, bytearray)) or len(audio_bytes) == 0:
        raise HTTPException(status_code=500, detail="generate 返回空音频")

    return audio_bytes


@router.post("/tts/", response_class=StreamingResponse)
async def tts(
    text: str = Form(...),
    language: str = Form("zh"),
    speed: Literal["low", "balanced", "fast"] = Form("balanced"),
    volume: Literal["small", "middle", "large"] = Form("middle"),
    output_format: OutputFormat = Form("mp3"),
    max_chars: int = Form(80),
    tts_style: int = Form(1),
):
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    try:
        tts_style = 1 if tts_style not in TTS_STYLE else tts_style
        userId, speakerId = TTS_STYLE[tts_style]

        audio_bytes = await process(
            text,
            userId,
            speakerId,
            speed,
            volume,
            output_format,
            max_chars,
        )

        return audio_response(audio_bytes, output_format)

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("tts failed")
        raise HTTPException(status_code=500, detail=f"tts failed: {e}")


@router.post("/tts2/", response_class=StreamingResponse)
async def tts2(
    text: str = Form(...),
    language: str = Form("zh"),
    speed: Literal["low", "balanced", "fast"] = Form("balanced"),
    volume: Literal["small", "middle", "large"] = Form("middle"),
    output_format: OutputFormat = Form("mp3"),
    max_chars: int = Form(80),
    userId: str = Form(...),
    speakerId: str = Form(...),
):
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    try:
        audio_bytes = await process(
            text,
            userId,
            speakerId,
            speed,
            volume,
            output_format,
            max_chars,
        )

        return audio_response(audio_bytes, output_format)

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("tts2 failed userId=%s speakerId=%s", userId, speakerId)
        raise HTTPException(status_code=500, detail=f"tts2 failed: {e}")


@router.post("/tts3/", response_class=StreamingResponse)
async def tts3(
    text: str = Form(...),
    language: str = Form("zh"),
    speed: Literal["low", "balanced", "fast"] = Form("balanced"),
    volume: Literal["small", "middle", "large"] = Form("middle"),
    output_format: OutputFormat = Form("mp3"),
    max_chars: int = Form(80),
    prompt_text: str = Form(...),
    prompt_audio: UploadFile = File(...),
):
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    if not prompt_text or not prompt_text.strip():
        raise HTTPException(status_code=400, detail="prompt_text 不能为空")
    if max_chars <= 0:
        raise HTTPException(status_code=400, detail="max_chars 必须大于 0")

    try:
        audio_bytes = await prompt_audio.read()
        audio_bytes = audio_bytes_to_wav_bytes(audio_bytes)
        check_audio_bytes(audio_bytes)

        waveform, sr = sf.read(io.BytesIO(audio_bytes))
        assert sr == 16000, "sample rate hardcoded in server"

        samples = np.array(waveform, dtype=np.float32)

        logger.info(
            "tts3 requested text_chars=%s prompt_chars=%s output_format=%s speed=%s volume=%s",
            len(text.strip()),
            len(prompt_text.strip()),
            output_format,
            speed,
            volume,
        )

        async with tts_semaphore:
            audio_bytes = await asyncio.to_thread(
                generate,
                reference_audio=samples,
                reference_text=prompt_text.strip(),
                target_text=text.strip(),
                max_chars=max_chars,
                output_format=output_format,
                volume=volume_to_linear(volume),
                speed=SPEED_MAP[speed],
            )

        if not isinstance(audio_bytes, (bytes, bytearray)) or len(audio_bytes) == 0:
            raise HTTPException(status_code=500, detail="generate 返回空音频")

        return audio_response(audio_bytes, output_format)

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("tts3 failed")
        raise HTTPException(status_code=500, detail=f"tts3 failed: {e}")
