
import numpy as np
import string
import random
import time
import subprocess

def audio_f2i(data, width=16):
    """将浮点数音频数据转换为整数音频数据。"""
    data = np.array(data)
    return np.int16(data * (2 ** (width - 1)))

def audio_i2f(data, width=16):
    """将整数音频数据转换为浮点数音频数据。"""
    data = np.array(data)
    return np.float32(data / (2 ** (width - 1)))

def read_audio_file(audio_file:str, rate: int = 16000):
    """读取音频文件数据并转换为PCM数组"""
    ffmpeg_cmd = [
        "ffmpeg",
        '-i', audio_file,
        '-f', 's16le',
        '-acodec', 'pcm_s16le',
        '-ar', str(rate),
        '-ac', '1',
        'pipe:']
    with subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False) as proc:
        stdout_data, stderr_data = proc.communicate()
    pcm_data = np.frombuffer(stdout_data, dtype=np.int16)
    return pcm_data

def read_audio_bytes(audio_bytes:bytes, rate: int = 16000):
    """将音频文件的二进制数据转换为PCM数组"""
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


import subprocess
from typing import Literal, Optional


AudioFormat = Literal[
    "mp3",
    "wav",
    "aac",
    "m4a",
    "opus",
    "ogg",
    "flac",
    "webm"
]


def pcm_to_codec_bytes(
    pcm_bytes: bytes,
    input_sample_rate: int,
    input_channels: int,
    output_format: AudioFormat = "mp3",
    config: Optional[dict] = None,
) -> bytes:
    """
    PCM(s16le) -> 主流音频编码

    Parameters
    ----------
    pcm_bytes : bytes
        输入 PCM 数据，格式必须是 s16le

    input_sample_rate : int
        输入 PCM 采样率，例如 16000 / 24000 / 44100

    input_channels : int
        输入 PCM 声道数，例如 1 / 2

    output_format : str
        输出格式:
            pcm / mp3 / wav / aac / m4a / opus / ogg / flac / webm

    config : dict
        输出配置:
        {
            "output_sample_rate": 24000,
            "output_channels": 1,
            "bit_rate": "128k",
            "quality": 2,
            "compression_level": 5,
            "application": "voip",
            "ffmpeg_loglevel": "error",
        }

    Returns
    -------
    bytes
        编码后的音频数据
    """

    config = config or {}

    output_sample_rate = config.get("output_sample_rate", input_sample_rate)
    output_channels = config.get("output_channels", input_channels)

    bit_rate = config.get("bit_rate", "128k")
    quality = config.get("quality", 2)
    compression_level = config.get("compression_level", 5)
    application = config.get("application", "voip")
    ffmpeg_loglevel = config.get("ffmpeg_loglevel", "error")

    if not pcm_bytes:
        raise ValueError("pcm_bytes is empty")

    if input_sample_rate <= 0:
        raise ValueError("input_sample_rate must be positive")

    if input_channels <= 0:
        raise ValueError("input_channels must be positive")

    if output_sample_rate <= 0:
        raise ValueError("output_sample_rate must be positive")

    if output_channels <= 0:
        raise ValueError("output_channels must be positive")

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", ffmpeg_loglevel,

        # 输入 PCM 配置
        "-f", "s16le",
        "-ar", str(input_sample_rate),
        "-ac", str(input_channels),
        "-i", "pipe:0",

        # 输出音频配置
        "-ar", str(output_sample_rate),
        "-ac", str(output_channels),
    ]

    if output_format == "pcm":
        ffmpeg_cmd += [
            "-codec:a", "pcm_s16le",
            "-f", "s16le",
            "pipe:1",
        ]

    elif output_format == "mp3":
        ffmpeg_cmd += [
            "-codec:a", "libmp3lame",
            "-b:a", bit_rate,
            "-q:a", str(quality),
            "-f", "mp3",
            "pipe:1",
        ]

    elif output_format == "wav":
        ffmpeg_cmd += [
            "-codec:a", "pcm_s16le",
            "-f", "wav",
            "pipe:1",
        ]

    elif output_format == "aac":
        ffmpeg_cmd += [
            "-codec:a", "aac",
            "-b:a", bit_rate,
            "-f", "adts",
            "pipe:1",
        ]

    elif output_format == "m4a":
        ffmpeg_cmd += [
            "-codec:a", "aac",
            "-b:a", bit_rate,
            "-movflags", "frag_keyframe+empty_moov",
            "-f", "mp4",
            "pipe:1",
        ]

    elif output_format == "opus":
        ffmpeg_cmd += [
            "-codec:a", "libopus",
            "-b:a", bit_rate,
            "-application", application,
            "-f", "ogg",
            "pipe:1",
        ]

    elif output_format == "ogg":
        ffmpeg_cmd += [
            "-codec:a", "libvorbis",
            "-q:a", str(config.get("ogg_quality", 5)),
            "-f", "ogg",
            "pipe:1",
        ]

    elif output_format == "flac":
        ffmpeg_cmd += [
            "-codec:a", "flac",
            "-compression_level", str(compression_level),
            "-f", "flac",
            "pipe:1",
        ]

    elif output_format == "webm":
        ffmpeg_cmd += [
            "-codec:a", "libopus",
            "-b:a", bit_rate,
            "-application", application,
            "-f", "webm",
            "pipe:1",
        ]

    else:
        raise ValueError(f"Unsupported output_format: {output_format}")

    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    audio_bytes, stderr_data = proc.communicate(input=pcm_bytes)

    if proc.returncode != 0:
        raise RuntimeError(
            stderr_data.decode("utf-8", errors="ignore")
        )

    return audio_bytes


def process_pcm_bytes(
    pcm_bytes: bytes,
    config: Optional[dict] = None,
) -> bytes:
    """
    PCM(s16le) 后处理：音量 / 语速

    config:
    {
        "sample_rate": 16000,
        "channels": 1,

        # 音量控制，三选一即可
        "volume": 1.0,        # 线性倍率，1.0不变，0.5减半，2.0放大
        "volume_db": 0.0,     # 分贝增益，例如 +6 / -6

        # 语速控制
        "speed": 1.0,         # 1.0不变，1.2加快，0.8变慢

        "ffmpeg_loglevel": "error",
    }
    """

    config = config or {}

    sample_rate = config.get("sample_rate", 16000)
    channels = config.get("channels", 1)
    volume = config.get("volume", None)
    volume_db = config.get("volume_db", None)
    speed = config.get("speed", 1.0)
    ffmpeg_loglevel = config.get("ffmpeg_loglevel", "error")

    filters = []

    # -------------------------
    # 音量
    # -------------------------
    if volume_db is not None:
        filters.append(f"volume={volume_db}dB")
    elif volume is not None:
        filters.append(f"volume={volume}")

    # -------------------------
    # 语速
    # atempo 单次范围是 0.5 ~ 2.0
    # 超过范围需要串联多个 atempo
    # -------------------------
    if speed != 1.0:
        if speed <= 0:
            raise ValueError("speed must be > 0")

        atempo_filters = build_atempo_filters(speed)
        filters.extend(atempo_filters)

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", ffmpeg_loglevel,
        "-f", "s16le",
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "-i", "pipe:0",
    ]

    if filters:
        ffmpeg_cmd += [
            "-af", ",".join(filters)
        ]

    ffmpeg_cmd += [
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "pipe:1",
    ]

    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    output_pcm, stderr_data = proc.communicate(input=pcm_bytes)

    if proc.returncode != 0:
        raise RuntimeError(
            stderr_data.decode("utf-8", errors="ignore")
        )

    return output_pcm


def build_atempo_filters(speed: float) -> list:
    """
    ffmpeg atempo 单个滤镜只支持 0.5 ~ 2.0。
    因此 speed > 2 或 speed < 0.5 时，需要拆成多个 atempo。
    """
    filters = []

    while speed > 2.0:
        filters.append("atempo=2.0")
        speed /= 2.0

    while speed < 0.5:
        filters.append("atempo=0.5")
        speed /= 0.5

    filters.append(f"atempo={speed:.6f}")

    return filters

if __name__ == "__main__":
    
    aduio_path = "prompt_16k.wav"
    pcm_data = read_audio_file(aduio_path)
    pcm_bytes = pcm_data.tobytes()
    pcm_bytes = process_pcm_bytes(
        pcm_bytes,
        config={
            "sample_rate": 16000,
            "channels": 1,
            "volume": 0.5,
            "speed": 0.8,
        }
    )
    
    for codec in ["mp3", "wav", "aac", "m4a", "opus",  "flac", "webm"]:
        print(f"Converting to {codec}...")
        output_bytes = pcm_to_codec_bytes(pcm_bytes, output_format=codec)
        with open(f"output.{codec}", "wb") as f:
            f.write(output_bytes)