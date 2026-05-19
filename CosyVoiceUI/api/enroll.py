import os
import json
import shutil

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .common import (
    CACHE_DIR,
    make_response,
    safe_name,
    get_user_dir,
    get_speaker_dir,
    get_prompt_paths,
    load_profile,
    validate_profile,
    decode_base64_file,
    check_avatar_bytes,
    audio_base64_to_checked_wav,
)


router = APIRouter(tags=["enroll"])


@router.get("/cache/audio/{userId}/{speakerId}")
def fetch_speaker_audio(userId: str, speakerId: str):
    audio_path, _, _ = get_prompt_paths(userId, speakerId, check_exists=True)

    return FileResponse(
        audio_path,
        media_type="audio/wav",
        filename=f"{speakerId}.wav",
    )


@router.get("/cache/avatar/{userId}/{speakerId}")
def fetch_speaker_avatar(userId: str, speakerId: str):
    _, _, avatar_path = get_prompt_paths(userId, speakerId, check_exists=False)

    if not os.path.exists(avatar_path):
        raise HTTPException(status_code=404, detail="头像不存在")

    return FileResponse(
        avatar_path,
        media_type="image/png",
        filename=f"{speakerId}.png",
    )


@router.get("/fetch_users")
def fetch_users():
    users = []

    if os.path.exists(CACHE_DIR):
        for name in os.listdir(CACHE_DIR):
            path = os.path.join(CACHE_DIR, name)
            if os.path.isdir(path):
                users.append(name)

    return make_response(result={"users": sorted(users)})


@router.post("/add_user/{userId}")
async def add_user(userId: str):
    userId = safe_name(userId, "userId")
    user_dir = get_user_dir(userId)

    if os.path.exists(user_dir):
        return make_response(msg="user already exists", result={"userId": userId})

    os.makedirs(user_dir, exist_ok=True)

    return make_response(msg="add user successfully", result={"userId": userId})


@router.post("/delete_user/{userId}")
async def delete_user(userId: str):
    userId = safe_name(userId, "userId")
    user_dir = get_user_dir(userId)

    if not os.path.exists(user_dir):
        return make_response(msg="user not exists", result={"userId": userId})

    shutil.rmtree(user_dir)

    return make_response(msg="delete user successfully", result={"userId": userId})


@router.get("/fetch_speakers/{userId}")
def fetch_speakers(userId: str):
    userId = safe_name(userId, "userId")
    user_dir = get_user_dir(userId)

    if not os.path.exists(user_dir):
        raise HTTPException(status_code=404, detail="user 不存在")

    speakers = []

    for speakerId in sorted(os.listdir(user_dir)):
        speaker_dir = os.path.join(user_dir, speakerId)

        if not os.path.isdir(speaker_dir):
            continue

        audio_path = os.path.join(speaker_dir, "audio.wav")
        profile_path = os.path.join(speaker_dir, "profile.json")
        avatar_path = os.path.join(speaker_dir, "avatar.png")

        if not os.path.exists(profile_path):
            continue

        try:
            profile = load_profile(profile_path)
        except Exception:
            continue

        speakers.append({
            "speakerId": speakerId,
            "profile": profile,
            "has_audio": os.path.exists(audio_path),
            "has_avatar": os.path.exists(avatar_path),
            "audio_url": f"/cache/audio/{userId}/{speakerId}" if os.path.exists(audio_path) else "",
            "avatar_url": f"/cache/avatar/{userId}/{speakerId}" if os.path.exists(avatar_path) else "",
        })

    return make_response(result={"userId": userId, "speakers": speakers})


@router.get("/fetch_speaker/{userId}/{speakerId}")
def fetch_speaker(userId: str, speakerId: str):
    userId = safe_name(userId, "userId")
    speakerId = safe_name(speakerId, "speakerId")

    audio_path, profile_path, avatar_path = get_prompt_paths(userId, speakerId, check_exists=True)
    profile = load_profile(profile_path)

    return make_response(
        result={
            "userId": userId,
            "speakerId": speakerId,
            "profile": profile,
            "has_audio": os.path.exists(audio_path),
            "has_avatar": os.path.exists(avatar_path),
            "audio_url": f"/cache/audio/{userId}/{speakerId}",
            "avatar_url": f"/cache/avatar/{userId}/{speakerId}" if os.path.exists(avatar_path) else "",
        }
    )


@router.post("/write_speaker")
async def write_speaker(request: Request):
    data: dict = await request.json()

    userId = safe_name(data.get("userId", ""), "userId")
    speakerId = safe_name(data.get("speakerId", ""), "speakerId")

    audio_base64 = data.get("audio_base64")
    avatar_base64 = data.get("avatar_base64")
    profile = data.get("profile")

    user_dir = get_user_dir(userId)
    speaker_dir = get_speaker_dir(userId, speakerId)

    is_new_speaker = not os.path.exists(speaker_dir)

    if is_new_speaker:
        if not audio_base64:
            raise HTTPException(status_code=400, detail="新增 speaker 时 audio_base64 必填")
        if not profile:
            raise HTTPException(status_code=400, detail="新增 speaker 时 profile 必填")

    if not any([audio_base64, avatar_base64, profile]):
        raise HTTPException(status_code=400, detail="audio_base64/avatar_base64/profile 至少传一个")

    os.makedirs(user_dir, exist_ok=True)
    os.makedirs(speaker_dir, exist_ok=True)

    audio_path = os.path.join(speaker_dir, "audio.wav")
    avatar_path = os.path.join(speaker_dir, "avatar.png")
    profile_path = os.path.join(speaker_dir, "profile.json")

    saved = {"audio": False, "avatar": False, "profile": False}
    audio_info = None
    avatar_kind = None

    if audio_base64:
        audio_bytes, audio_info = audio_base64_to_checked_wav(audio_base64)

        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        saved["audio"] = True

    if avatar_base64:
        avatar_bytes = decode_base64_file(avatar_base64, "avatar_base64")
        avatar_kind = check_avatar_bytes(avatar_bytes)

        with open(avatar_path, "wb") as f:
            f.write(avatar_bytes)

        saved["avatar"] = True

    if profile is not None:
        checked_profile = validate_profile(profile, userId, speakerId)

        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(checked_profile, f, ensure_ascii=False, indent=2)

        saved["profile"] = True

    if not os.path.exists(audio_path):
        raise HTTPException(status_code=400, detail="speaker 缺少 audio.wav")

    if not os.path.exists(profile_path):
        raise HTTPException(status_code=400, detail="speaker 缺少 profile.json")

    msg = "add speaker successfully" if is_new_speaker else "update speaker successfully"

    return make_response(
        msg=msg,
        result={
            "userId": userId,
            "speakerId": speakerId,
            "is_new_speaker": is_new_speaker,
            "saved": saved,
            "audio_info": audio_info,
            "avatar_kind": avatar_kind,
            "audio_url": f"/cache/audio/{userId}/{speakerId}",
            "avatar_url": f"/cache/avatar/{userId}/{speakerId}" if os.path.exists(avatar_path) else "",
        },
    )


@router.post("/delete_speaker/{userId}/{speakerId}")
async def delete_speaker(userId: str, speakerId: str):
    userId = safe_name(userId, "userId")
    speakerId = safe_name(speakerId, "speakerId")

    speaker_dir = get_speaker_dir(userId, speakerId)

    if not os.path.exists(speaker_dir):
        return make_response(
            msg="speaker not exists",
            result={"userId": userId, "speakerId": speakerId},
        )

    shutil.rmtree(speaker_dir)

    return make_response(
        msg="delete speaker successfully",
        result={"userId": userId, "speakerId": speakerId},
    )