import os

# 注册音频规范
MAX_AUDIO_SECONDS = 5.0
REQUIRED_SR = 16000
REQUIRED_CHANNELS = 1

# 服务配置
PWD = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(PWD, "cache")
WEB_DIR = os.path.join(PWD, "templates")
SERVER_PORT = 10100
SSL_CERT = os.path.join(PWD, "ssl/server.crt")
SSL_KEY = os.path.join(PWD, "ssl/server.key")
USE_SSL = True

