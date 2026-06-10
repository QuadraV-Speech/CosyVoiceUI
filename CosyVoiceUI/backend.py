
import logging
import numpy as np 
import requests
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from .audio_factory import pcm_to_codec_bytes, audio_f2i, process_pcm_bytes
from .config import (
    BACKEND_MODEL_NAME,
    BACKEND_SEGMENT_WORKERS,
    BACKEND_SERVER_URL,
    BACKEND_TIMEOUT_SECONDS,
)
from .split import split_text_greedy_by_punctuation
import os

logger = logging.getLogger(__name__)
_thread_local = threading.local()


def get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
    return session


def prepare_request(
    waveform:np.ndarray,
    reference_text: str,
    target_text: str,
    sample_rate: int = 16000,
    padding_duration: int = None,
):
    assert len(waveform.shape) == 1, "waveform should be 1D"
    lengths = np.array([[len(waveform)]], dtype=np.int32)
    if padding_duration:
        # padding to nearset 10 seconds
        samples = np.zeros(
            (
                1,
                padding_duration
                * sample_rate
                * ((int(len(waveform) / sample_rate) // padding_duration) + 1),
            ),
            dtype=np.float32,
        )

        samples[0, : len(waveform)] = waveform
    else:
        samples = waveform

    samples = samples.reshape(1, -1).astype(np.float32)

    data = {
        "inputs": [
            {
                "name": "reference_wav",
                "shape": samples.shape,
                "datatype": "FP32",
                "data": samples.tolist()
            },
            {
                "name": "reference_wav_len",
                "shape": lengths.shape,
                "datatype": "INT32",
                "data": lengths.tolist(),
            },
            {
                "name": "reference_text",
                "shape": [1, 1],
                "datatype": "BYTES",
                "data": [reference_text]
            },
            {
                "name": "target_text",
                "shape": [1, 1],
                "datatype": "BYTES",
                "data": [target_text]
            }
        ]
    }

    return data


def infer_segment(url: str, reference_audio: np.ndarray, reference_text: str, text: str, idx: int) -> np.ndarray:
    data = prepare_request(reference_audio, reference_text, text)

    rsp = get_session().post(
        url,
        headers={"Content-Type": "application/json"},
        json=data,
        verify=False,
        params={"request_id": str(idx)},
        timeout=BACKEND_TIMEOUT_SECONDS,
    )
    rsp.raise_for_status()

    result = rsp.json()
    outputs = result.get("outputs") or []
    if not outputs or "data" not in outputs[0]:
        raise RuntimeError("backend response missing outputs[0].data")

    return audio_f2i(outputs[0]["data"])


def generate(
    reference_audio: np.ndarray,
    reference_text: str,
    target_text: str,
    max_chars: int = 80,
    output_format: str = "mp3",
    volume: float = 1.0,
    speed: float = 1.0
    
):
    start_time = time.perf_counter()
    url = f"{BACKEND_SERVER_URL}/v2/models/{BACKEND_MODEL_NAME}/infer"

    text_list = split_text_greedy_by_punctuation(target_text, max_chars=max_chars)
    if not text_list:
        raise ValueError("target_text is empty")

    logger.info(
        "tts backend request segments=%s max_chars=%s output_format=%s speed=%.3f volume=%.3f",
        len(text_list),
        max_chars,
        output_format,
        speed,
        volume,
    )

    workers = max(1, min(BACKEND_SEGMENT_WORKERS, len(text_list)))

    if workers == 1:
        all_audio = [
            infer_segment(url, reference_audio, reference_text, text, idx)
            for idx, text in enumerate(text_list)
        ]
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tts-segment") as executor:
            futures = [
                executor.submit(infer_segment, url, reference_audio, reference_text, text, idx)
                for idx, text in enumerate(text_list)
            ]
            all_audio = [future.result() for future in futures]

    audio = np.concatenate(all_audio, axis=0)

    pcm_bytes = audio.tobytes()
    
    # 调整音量/语速
    pcm_bytes = process_pcm_bytes(
        pcm_bytes=pcm_bytes,
        config={
            "volume": volume,
            "speed": speed,
        }
    )
    
    # 调整编码
    input_sample_rate = 24000
    audio_bytes = pcm_to_codec_bytes(
        pcm_bytes=pcm_bytes,
        input_sample_rate=input_sample_rate,
        input_channels=1,
        output_format=output_format,
        config={"output_sample_rate": 16000}
    )
    logger.info(
        "tts backend completed segments=%s bytes=%s duration_ms=%.2f",
        len(text_list),
        len(audio_bytes),
        (time.perf_counter() - start_time) * 1000,
    )
    return audio_bytes
    



if __name__ == "__main__":
    
    from .utils import read_audio_file, audio_i2f
    pwd = os.path.dirname(os.path.abspath(__file__))
    audio_path = f"{pwd}/examples/prompt_16k.wav"
    audio_data = read_audio_file(audio_path)
    audio_data = audio_i2f(audio_data)
    audio_text = "希望你以后能够做的比我还好呦。"
    
    target_text = """大家好，Good morning everyone! 今天我想和大家分享一个主题——拥抱变化，持续成长（Embrace Change, Keep Growing）。在这个快速发展的时代，technology is changing everything around us. 从人工智能到智能设备，从在线教育到远程办公，我们每天都在面对新的挑战和新的机会。很多时候，变化会让人感到不安，因为它意味着我们需要离开舒适区（comfort zone）。但是，正是这些变化，推动着我们不断进步。There is a famous saying: "Life begins at the end of your comfort zone." """
    
    output_format = "aac"
    audio_bytes = generate(
        reference_audio=audio_data,
        reference_text=audio_text,
        target_text=target_text,
        output_format=output_format,
        volume=1.2,
        speed=0.8
    )
    with open(f"output.{output_format}", "wb") as f:
        f.write(audio_bytes)
        
    
    
    
