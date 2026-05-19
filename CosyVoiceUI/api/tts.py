import io
import asyncio
import traceback
from typing import Literal

import numpy as np
import soundfile as sf
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from ..backend import generate
from ..utils import postprocess_audio, audio_bytes_to_wav_bytes
from .common import (
    TTS_STYLE,
    get_prompt_paths,
    load_profile,
    check_audio_bytes,
)


router = APIRouter(tags=["tts"])


async def process(
    text: str,
    userId: str,
    speakerId: str,
    speed: Literal["low", "balanced", "fast"] = "balanced",
    volume: Literal["small", "middle", "large"] = "middle",
):
    text = text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    audio_path, profile_path, _ = get_prompt_paths(userId, speakerId, check_exists=True)

    waveform, sr = sf.read(audio_path)
    assert sr == 16000, "sample rate hardcoded in server"

    samples = np.array(waveform, dtype=np.float32)

    profile = load_profile(profile_path)
    audio_text = profile.get("text", "").strip()

    if not audio_text:
        raise HTTPException(status_code=400, detail="speaker profile.text 不能为空")

    mp3_bytes = await asyncio.to_thread(
        generate,
        samples,
        audio_text,
        text,
    )

    if not isinstance(mp3_bytes, (bytes, bytearray)) or len(mp3_bytes) == 0:
        raise HTTPException(status_code=500, detail="generate 返回空音频")

    if speed != "balanced" or volume != "middle":
        mp3_bytes = await asyncio.to_thread(
            postprocess_audio,
            mp3_bytes,
            speed,
            volume,
        )

    return mp3_bytes


@router.post("/tts/", response_class=StreamingResponse)
async def tts(
    text: str = Form(...),
    language: str = Form("zh"),
    speed: Literal["low", "balanced", "fast"] = Form("balanced"),
    volume: Literal["small", "middle", "large"] = Form("middle"),
    tts_style: int = Form(1),
):
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    try:
        tts_style = 1 if tts_style not in TTS_STYLE else tts_style
        userId, speakerId = TTS_STYLE[tts_style]

        mp3_bytes = await process(text, userId, speakerId, speed, volume)

        return StreamingResponse(
            io.BytesIO(mp3_bytes),
            media_type="audio/mpeg",
            headers={"Content-Disposition": 'inline; filename="tts.mp3"'},
        )

    except HTTPException:
        raise

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"tts failed: {e}")


@router.post("/tts2/", response_class=StreamingResponse)
async def tts2(
    text: str = Form(...),
    language: str = Form("zh"),
    speed: Literal["low", "balanced", "fast"] = Form("balanced"),
    volume: Literal["small", "middle", "large"] = Form("middle"),
    userId: str = Form(...),
    speakerId: str = Form(...),
):
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    try:
        mp3_bytes = await process(text, userId, speakerId, speed, volume)

        return StreamingResponse(
            io.BytesIO(mp3_bytes),
            media_type="audio/mpeg",
            headers={"Content-Disposition": 'inline; filename="tts.mp3"'},
        )

    except HTTPException:
        raise

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"tts2 failed: {e}")


@router.post("/tts3/", response_class=StreamingResponse)
async def tts3(
    text: str = Form(...),
    language: str = Form("zh"),
    speed: Literal["low", "balanced", "fast"] = Form("balanced"),
    volume: Literal["small", "middle", "large"] = Form("middle"),
    prompt_text: str = Form(...),
    prompt_audio: UploadFile = File(...),
):
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    if not prompt_text or not prompt_text.strip():
        raise HTTPException(status_code=400, detail="prompt_text 不能为空")

    try:
        audio_bytes = await prompt_audio.read()
        audio_bytes = audio_bytes_to_wav_bytes(audio_bytes)
        check_audio_bytes(audio_bytes)

        waveform, sr = sf.read(io.BytesIO(audio_bytes))
        assert sr == 16000, "sample rate hardcoded in server"

        samples = np.array(waveform, dtype=np.float32)

        mp3_bytes = await asyncio.to_thread(
            generate,
            samples,
            prompt_text.strip(),
            text.strip(),
        )

        if not isinstance(mp3_bytes, (bytes, bytearray)) or len(mp3_bytes) == 0:
            raise HTTPException(status_code=500, detail="generate 返回空音频")

        if speed != "balanced" or volume != "middle":
            mp3_bytes = await asyncio.to_thread(
                postprocess_audio,
                mp3_bytes,
                speed,
                volume,
            )

        return StreamingResponse(
            io.BytesIO(mp3_bytes),
            media_type="audio/mpeg",
            headers={"Content-Disposition": 'inline; filename="tts.mp3"'},
        )

    except HTTPException:
        raise

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"tts3 failed: {e}")