# CosyVoice tts 接口 文档


## API 端点

### 1. 文字转语音 (TTS) 接口

#### 1.1. TTS 接口 1：内置说话人 (`POST /tts/`)

使用预设的内置说话人进行语音合成。说话人通过 `tts_style` 参数的编号选择。

**请求体参数:**
- `text` (string, 必填): 需要合成的文本。
- `language` (string, 可选, 默认 `zh`): 语言。
- `speed` (enum, 可选, 默认 `balanced`): 语速 (`low`, `balanced`, `fast`)。
- `volume` (enum, 可选, 默认 `middle`): 音量 (`small`, `middle`, `large`)。
- `output_format` (enum, 可选, 默认 `mp3`): 输出格式 (`pcm`, `mp3`, `wav`, `aac`, `m4a`, `opus`, `ogg`, `flac`, `webm`)。
- `max_chars` (int, 可选, 默认 `80`): 长文本分段时每段最大字符数。
- `tts_style` (int, 可选, 默认 `1`): 内置说话人编号 (1, 2, 3 等)。

**请求示例:**
```bash
curl -X POST "http://$address:10100/tts/" \
     -F "text=你好，这是一个测试。nice to meet you!" \
     -F "tts_style=1" \
     -F "speed=balanced" \
     -F "volume=middle" \
     -F "output_format=mp3" \
     --output tts_output_builtin.mp3
```

**响应:** 返回指定格式的音频流。

#### 1.2. TTS 接口 2：自定义说话人 (`POST /tts2/`)

使用通过后台管理接口注册的自定义说话人进行语音合成。说话人通过 `userId` 和 `speakerId` 参数指定。

请在后台注册你的说话人音色，
后台地址：https://$address/cosyvoice/

**请求体参数:**
- `text` (string, 必填): 需要合成的文本。
- `language` (string, 可选, 默认 `zh`): 语言。
- `speed` (enum, 可选, 默认 `balanced`): 语速 (`low`, `balanced`, `fast`)。
- `volume` (enum, 可选, 默认 `middle`): 音量 (`small`, `middle`, `large`)。
- `output_format` (enum, 可选, 默认 `mp3`): 输出格式 (`pcm`, `mp3`, `wav`, `aac`, `m4a`, `opus`, `ogg`, `flac`, `webm`)。
- `max_chars` (int, 可选, 默认 `80`): 长文本分段时每段最大字符数。
- `userId` (string, 必填): 用户 ID。
- `speakerId` (string, 必填): 说话人 ID。

**请求示例:**
```bash
curl -X POST "http://localhost:10100/tts2/" \
     -F "text=你好，这是一个测试。nice to meet you!" \
     -F "userId=common" \
     -F "speakerId=speaker_2" \
     -F "speed=balanced" \
     -F "volume=middle" \
     -F "output_format=mp3" \
     --output tts_output_custom.mp3
```

**响应:** 返回指定格式的音频流。

#### 1.3. TTS 接口 3：直接上传提示音频和文本 (`POST /tts3/`)

直接上传提示音频 (`prompt_audio`) 和其对应的文本 (`prompt_text`)，用于即时定制说话人并合成语音。

**请求体参数:**
- `text` (string, 必填): 需要合成的文本。
- `prompt_text` (string, 必填): 提示音频的标注文本。
- `prompt_audio` (file, 必填): 提示音频文件 (例如 `.wav`, `.mp3` 等，将被转换为 16kHz 单声道 WAV)。
- `language` (string, 可选, 默认 `zh`): 语言。
- `speed` (enum, 可选, 默认 `balanced`): 语速 (`low`, `balanced`, `fast`)。
- `volume` (enum, 可选, 默认 `middle`): 音量 (`small`, `middle`, `large`)。
- `output_format` (enum, 可选, 默认 `mp3`): 输出格式 (`pcm`, `mp3`, `wav`, `aac`, `m4a`, `opus`, `ogg`, `flac`, `webm`)。
- `max_chars` (int, 可选, 默认 `80`): 长文本分段时每段最大字符数。

**请求示例:**
```bash
curl -X POST "http://$address:10100/tts3/" \
     -F "text=你好，这是一个测试。nice to meet you!" \
     -F "prompt_text=希望你以后过得比我还好哟" \
     -F "prompt_audio=@./zero_shot_prompt.wav;type=audio/wav" \
     -F "speed=balanced" \
     -F "volume=middle" \
     -F "output_format=mp3" \
     --output tts_output_direct.mp3
```
