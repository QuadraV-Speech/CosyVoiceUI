
from pydub import AudioSegment
import io
import subprocess
import numpy as np


SPEED_MAP = {
    "low": 0.85,
    "balanced": 1.0,
    "fast": 1.15,
}

VOLUME_MAP = {
    "small": -6.0,
    "middle": 0.0,
    "large": 6.0,
}


def change_speed(audio: AudioSegment, speed: float) -> AudioSegment:
    if speed <= 0:
        raise ValueError("speed must be > 0")

    if abs(speed - 1.0) < 1e-6:
        return audio

    original_frame_rate = audio.frame_rate
    new_frame_rate = int(original_frame_rate * speed)

    return audio._spawn(
        audio.raw_data,
        overrides={"frame_rate": new_frame_rate}
    ).set_frame_rate(original_frame_rate)


def change_volume(audio: AudioSegment, gain_db: float) -> AudioSegment:
    if abs(gain_db) < 1e-6:
        return audio
    return audio + gain_db


def postprocess_audio(mp3_bytes: bytes, speed: str, volume: str) -> bytes:
    # 默认值直接返回，不做任何处理
    if speed == "balanced" and volume == "middle":
        return mp3_bytes

    audio = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")

    if speed != "balanced":
        audio = change_speed(audio, SPEED_MAP[speed])

    if volume != "middle":
        audio = change_volume(audio, VOLUME_MAP[volume])

    out_buf = io.BytesIO()
    audio.export(out_buf, format="mp3")
    return out_buf.getvalue()


def audio_f2i(data, width=16):
    """将浮点数音频数据转换为整数音频数据。"""
    data = np.array(data)
    return np.int16(data * (2 ** (width - 1)))

def audio_i2f(data, width=16):
    """将整数音频数据转换为浮点数音频数据。"""
    data = np.array(data)
    return np.float32(data / (2 ** (width - 1)))


def pcm_to_mp3_bytes(pcm_data, sample_rate=16000, bit_rate="128k", quality=2):
    """
    Converts PCM audio data to MP3 format with compression.

    Parameters:
    pcm_data (bytes): The PCM audio data to convert.
    bit_rate (str): Bitrate of the output MP3 (e.g., "128k", "192k", "256k").
    quality (int): The quality level for MP3 encoding (lower is better quality; 0 is best, 9 is worst).

    Returns:
    bytes: The MP3 audio data in byte format.
    """

    # Set up the ffmpeg command to convert PCM to MP3 with compression
    ffmpeg_cmd = [
        'ffmpeg',
        '-f', 's16le',          # Format of the input (signed 16-bit little-endian PCM)
        '-ar', str(sample_rate),           # Sample rate (16kHz)
        '-ac', '1',             # Mono audio (1 channel)
        '-i', 'pipe:0',         # Input comes from stdin (pipe)
        '-ab', bit_rate,        # Set the bitrate (e.g., "128k")
        '-q:a', str(quality),   # Quality setting for MP3 encoding (0 for best quality, 9 for worst)
        '-f', 'mp3',            # Output format (MP3)
        'pipe:1'                # Output goes to stdout (pipe)
    ]

    # Start the subprocess to run ffmpeg and convert PCM to MP3
    with subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        # Convert the PCM data to MP3 by passing it through stdin
        mp3_bytes, stderr_data = proc.communicate(input=pcm_data)

    # Return the MP3 data in byte format
    return mp3_bytes


def read_audio_file(audio_file):
    """读取音频文件数据并转换为PCM格式。"""
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', audio_file,
        '-f', 's16le',
        '-acodec', 'pcm_s16le',
        '-ar', '16k',
        '-ac', '1',
        'pipe:']
    with subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False) as proc:
        stdout_data, stderr_data = proc.communicate()
    pcm_data = np.frombuffer(stdout_data, dtype=np.int16)
    return pcm_data

def read_audio_bytes(audio_bytes:bytes, rate: int = 16000):
    ffmpeg_cmd = [
    "ffmpeg",
    '-i', 'pipe:0',  
    '-f', 's16le',
    '-acodec', 'pcm_s16le',
    '-ar', str(rate),
    '-ac', '1',
    'pipe:1' ]
    with subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False) as proc:
        stdout_data, stderr_data = proc.communicate(input=audio_bytes)
    pcm_data = np.frombuffer(stdout_data, dtype=np.int16)
    return pcm_data


def audio_bytes_to_wav_bytes(audio_bytes: bytes, rate: int = 16000) -> bytes:
    """
    将任意 ffmpeg 支持的音频 bytes 转换为 WAV bytes。

    Args:
        audio_bytes: 输入音频文件的二进制数据，例如 mp3/m4a/webm/wav 等
        rate: 输出 WAV 的采样率，默认 16000

    Returns:
        WAV 格式的二进制数据
    """
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",
        "-f", "wav",
        "-acodec", "pcm_s16le",
        "-ar", str(rate),
        "-ac", "1",
        "pipe:1",
    ]

    with subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as proc:
        stdout_data, stderr_data = proc.communicate(input=audio_bytes)

    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 转换失败: {stderr_data.decode(errors='ignore')}"
        )

    return stdout_data


def generate_random_string(n):
    import string
    import random
    letters = string.ascii_letters + string.digits
    random_string = ''.join(random.choice(letters) for i in range(n))
    return random_string
