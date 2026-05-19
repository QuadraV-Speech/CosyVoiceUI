import os
import re
import io
import json
import time
import base64
import imghdr
from typing import Optional

import soundfile as sf
from fastapi import HTTPException

from ..utils import audio_bytes_to_wav_bytes
from ..config import CACHE_DIR, WEB_DIR, MAX_AUDIO_SECONDS, REQUIRED_SR, REQUIRED_CHANNELS



os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(WEB_DIR, exist_ok=True)


TTS_STYLE = {
    1: ["common", "speaker_1"],
    2: ["common", "speaker_2"],
    3: ["common", "speaker_3"],
}



NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")


def make_response(status: str = "success", msg: str = "", result: Optional[dict] = None):
    return {
        "status": status,
        "msg": msg,
        "result": result or {},
    }


def safe_name(name: str, field: str = "name") -> str:
    if not name or not isinstance(name, str):
        raise HTTPException(status_code=400, detail=f"{field} 不能为空")

    name = name.strip()

    if not NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=400,
            detail=f"{field} 非法，只允许字母、数字、下划线、中划线、点，长度 1-64",
        )

    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail=f"{field} 包含非法路径字符")

    return name


def get_user_dir(userId: str) -> str:
    userId = safe_name(userId, "userId")
    return os.path.join(CACHE_DIR, userId)


def get_speaker_dir(userId: str, speakerId: str) -> str:
    userId = safe_name(userId, "userId")
    speakerId = safe_name(speakerId, "speakerId")
    return os.path.join(CACHE_DIR, userId, speakerId)


def get_prompt_paths(userId: str, speakerId: str, check_exists: bool = True):
    speaker_dir = get_speaker_dir(userId, speakerId)

    audio_path = os.path.join(speaker_dir, "audio.wav")
    profile_path = os.path.join(speaker_dir, "profile.json")
    avatar_path = os.path.join(speaker_dir, "avatar.png")

    if check_exists:
        if not os.path.exists(speaker_dir):
            raise HTTPException(status_code=404, detail="speaker 不存在")
        if not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail="音频不存在")
        if not os.path.exists(profile_path):
            raise HTTPException(status_code=404, detail="profile 不存在")

    return audio_path, profile_path, avatar_path


def load_profile(profile_path: str):
    if not os.path.exists(profile_path):
        raise HTTPException(status_code=404, detail="profile 不存在")

    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    return {
        "userId": profile.get("userId", ""),
        "speakerId": profile.get("speakerId", ""),
        "nickname": profile.get("nickname", ""),
        "gender": profile.get("gender", "unknown"),
        "text": profile.get("text", ""),
        "discription": profile.get("discription", ""),
        "update_time": profile.get("update_time", 0),
        "update_time_str": profile.get("update_time_str", ""),
    }


def validate_profile(profile: dict, userId: str, speakerId: str) -> dict:
    if not isinstance(profile, dict):
        raise HTTPException(status_code=400, detail="profile 必须是 dict")

    nickname = str(profile.get("nickname", "")).strip()
    text = str(profile.get("text", "")).strip()

    if not nickname:
        raise HTTPException(status_code=400, detail="profile.nickname 不能为空")

    if not text:
        raise HTTPException(status_code=400, detail="profile.text 不能为空，也就是 prompt audio 的标注文本不能为空")

    profile_speaker_id = str(profile.get("speakerId") or speakerId).strip()
    profile_speaker_id = safe_name(profile_speaker_id, "profile.speakerId")

    if profile_speaker_id != speakerId:
        raise HTTPException(status_code=400, detail="profile.speakerId 必须和接口 speakerId 一致")

    gender = profile.get("gender", "unknown")
    if gender not in ["male", "female", "unknown"]:
        gender = "unknown"

    now = int(time.time())
    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))

    return {
        "userId": userId,
        "speakerId": speakerId,
        "nickname": nickname,
        "gender": gender,
        "text": text,
        "discription": str(profile.get("discription", "")).strip(),
        "update_time": now,
        "update_time_str": now_str,
    }


def strip_base64_header(data: str) -> str:
    if not data:
        return data

    data = data.strip()

    if data.startswith("data:") and "," in data:
        return data.split(",", 1)[1]

    return data


def decode_base64_file(data: str, field: str) -> bytes:
    if not data:
        raise HTTPException(status_code=400, detail=f"{field} 不能为空")

    try:
        raw = base64.b64decode(strip_base64_header(data), validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail=f"{field} 不是合法 base64")

    if len(raw) == 0:
        raise HTTPException(status_code=400, detail=f"{field} 内容为空")

    return raw


def check_audio_bytes(audio_bytes: bytes):
    try:
        with sf.SoundFile(io.BytesIO(audio_bytes)) as f:
            sr = f.samplerate
            channels = f.channels
            frames = len(f)
            duration = frames / float(sr)
    except Exception:
        raise HTTPException(status_code=400, detail="audio 不是合法音频文件，建议上传 wav")

    if sr != REQUIRED_SR:
        raise HTTPException(status_code=400, detail=f"audio 采样率必须是 {REQUIRED_SR}，当前是 {sr}")

    if channels != REQUIRED_CHANNELS:
        raise HTTPException(status_code=400, detail=f"audio 必须是单声道，当前 channels={channels}")

    if duration > MAX_AUDIO_SECONDS:
        raise HTTPException(status_code=400, detail=f"audio 时长不能超过 {MAX_AUDIO_SECONDS}s，当前 {duration:.2f}s")

    return {
        "sample_rate": sr,
        "channels": channels,
        "duration": round(duration, 3),
    }


def check_avatar_bytes(avatar_bytes: bytes):
    kind = imghdr.what(None, avatar_bytes)

    if kind not in ["png", "jpeg", "jpg"]:
        raise HTTPException(status_code=400, detail="avatar 只支持 png/jpg/jpeg")

    return kind


def audio_base64_to_checked_wav(audio_base64: str) -> tuple[bytes, dict]:
    audio_bytes = decode_base64_file(audio_base64, "audio_base64")
    audio_bytes = audio_bytes_to_wav_bytes(audio_bytes)
    audio_info = check_audio_bytes(audio_bytes)
    return audio_bytes, audio_info