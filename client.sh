curl -X POST "http://127.0.0.1:10090/tts/" \
    -F "text=你好，我是语音助手，我的名字叫玛丽，很高心为您服务" \
    -F "language=zh" -F "tts_style=1" -F "speed=balanced" -F "volume=middle" -F "codec=wav" \
    --output /data/wangwei/ai_speech_server/CosyVoiceUI/CosyVoiceUI/cache/common/speaker_1/audio.wav



# curl -X POST "http://mass.dev.hitecloud.cn:10100/tts/" \
# -F "text=然而，想象力，那是我们思维的翅膀。" \
# -F "language=zh" \
# -F "tts_style=2" \
# -F "speed=balanced" \
# -F "volume=middle" \
# -F "codec=mp3" \
# --output output.mp3