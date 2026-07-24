#!/usr/bin/env bash

# CosyVoiceUI curl 调用示例
#
# 默认服务地址：http://127.0.0.1:10090
# 请根据需要单独复制并运行下面的某一段命令。
#
# speed 可选值：low、balanced、fast
# volume 可选值：small、middle、large
# output_format 可选值：mp3、wav、aac、m4a、opus、ogg、flac、webm、pcm


# ============================================================
# 示例 1：使用内置音色合成 MP3
# ============================================================
# tts_style 对应内置音色编号，当前可使用 1、2、3、4。

curl --fail-with-body --silent --show-error \
  -X POST "http://127.0.0.1:10090/tts/" \
  -F "text=你好，我是 CosyVoice 语音助手，很高兴为您服务。" \
  -F "language=zh" \
  -F "tts_style=1" \
  -F "speed=balanced" \
  -F "volume=middle" \
  -F "output_format=mp3" \
  -F "max_chars=80" \
  --output tts_builtin.mp3


# ============================================================
# 示例 2：使用内置音色合成 WAV
# ============================================================
# 这里使用 2 号音色、慢速和较大音量。

curl --fail-with-body --silent --show-error \
  -X POST "http://127.0.0.1:10090/tts/" \
  -F "text=然而，想象力是我们思维的翅膀。" \
  -F "language=zh" \
  -F "tts_style=2" \
  -F "speed=low" \
  -F "volume=large" \
  -F "output_format=wav" \
  -F "max_chars=80" \
  --output tts_builtin.wav


# ============================================================
# 示例 3：使用已经注册的自定义音色
# ============================================================
# userId 和 speakerId 必须是后台已经存在的用户及音色。

curl --fail-with-body --silent --show-error \
  -X POST "http://127.0.0.1:10090/tts2/" \
  -F "text=你好，这是自定义音色合成测试。Nice to meet you!" \
  -F "language=zh" \
  -F "userId=common" \
  -F "speakerId=speaker_2" \
  -F "speed=balanced" \
  -F "volume=middle" \
  -F "output_format=mp3" \
  -F "max_chars=80" \
  --output tts_custom.mp3


# ============================================================
# 示例 4：直接上传参考音频进行音色克隆
# ============================================================
# 运行前请准备 ./prompt.wav。
# prompt_text 必须准确填写参考音频中说出的原文。

curl --fail-with-body --silent --show-error \
  -X POST "http://127.0.0.1:10090/tts3/" \
  -F "text=你好，这是上传参考音频的语音合成测试。" \
  -F "prompt_text=这里填写参考音频中说出的原文。" \
  -F "prompt_audio=@./prompt.wav;type=audio/wav" \
  -F "language=zh" \
  -F "speed=balanced" \
  -F "volume=middle" \
  -F "output_format=mp3" \
  -F "max_chars=80" \
  --output tts_prompt.mp3


# ============================================================
# 示例 5：查询所有用户
# ============================================================

curl --fail-with-body --silent --show-error \
  "http://127.0.0.1:10090/fetch_users"


# ============================================================
# 示例 6：查询 common 用户下的所有音色
# ============================================================

curl --fail-with-body --silent --show-error \
  "http://127.0.0.1:10090/fetch_speakers/common"
