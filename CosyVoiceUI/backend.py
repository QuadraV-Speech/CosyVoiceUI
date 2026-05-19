
import numpy as np 
import requests
from .utils import pcm_to_mp3_bytes, audio_f2i
import os

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


def generate(
    reference_audio:np.ndarray,
    reference_text: str,
    target_text: str,
):
    
    """
    reference_audio: 1D numpy array, float32, [-1, 1]
    reference_text: str, reference audio 对应的文本内容
    target_text: str, 需要合成的文本内容
    """
    
    
    server_url = "http://localhost:18000"
    model_name = "cosyvoice3"
    url = f"{server_url}/v2/models/{model_name}/infer"
    
    
    
    data = prepare_request(reference_audio, reference_text, target_text)
    
    rsp = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json=data,
        verify=False,
        params={"request_id": '0'}
    )
    result = rsp.json()
    audio = result["outputs"][0]["data"]
    audio = audio_f2i(audio)
    sample_rate = 24000
    mp3_bytes = pcm_to_mp3_bytes(audio.tobytes(), sample_rate=sample_rate)
    return mp3_bytes
    



if __name__ == "__main__":
    
    from .utils import read_audio_file, audio_i2f
    pwd = os.path.dirname(os.path.abspath(__file__))
    audio_path = f"{pwd}/examples/prompt_16k.wav"
    audio_data = read_audio_file(audio_path)
    audio_data = audio_i2f(audio_data)
    audio_text = "希望你以后能够做的比我还好呦。"
    
    target_text = "欢迎使用CosyVoice语音合成系统，这是一段测试文本。"
    
    mp3_bytes = generate(audio_data, audio_text, target_text)
    with open("output.mp3", "wb") as f:
        f.write(mp3_bytes)
    
    