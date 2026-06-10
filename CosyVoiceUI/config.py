import os


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# 注册音频规范
MAX_AUDIO_SECONDS = env_float("COSYVOICE_MAX_AUDIO_SECONDS", 20.0)
REQUIRED_SR = env_int("COSYVOICE_REQUIRED_SR", 16000)
REQUIRED_CHANNELS = env_int("COSYVOICE_REQUIRED_CHANNELS", 1)

# 服务配置
PWD = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(PWD, "cache")
WEB_DIR = os.path.join(PWD, "templates")
SERVER_PORT = env_int("COSYVOICE_SERVER_PORT", 10100)
SSL_CERT = os.path.join(PWD, "ssl/server.crt")
SSL_KEY = os.path.join(PWD, "ssl/server.key")
USE_SSL = env_bool("COSYVOICE_USE_SSL", False)
ENABLE_RELOAD = env_bool("COSYVOICE_RELOAD", False)

# 日志配置
LOG_DIR = os.getenv("COSYVOICE_LOG_DIR", os.path.join(PWD, "..", "tmp"))
LOG_LEVEL = os.getenv("COSYVOICE_LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("COSYVOICE_LOG_FILE", os.path.join(LOG_DIR, "server.log"))
LOG_MAX_BYTES = env_int("COSYVOICE_LOG_MAX_BYTES", 20 * 1024 * 1024)
LOG_BACKUP_COUNT = env_int("COSYVOICE_LOG_BACKUP_COUNT", 5)
ACCESS_LOG = env_bool("COSYVOICE_ACCESS_LOG", True)

# TTS 后端配置
BACKEND_SERVER_URL = os.getenv("COSYVOICE_BACKEND_SERVER_URL", "http://8.147.106.19:18000")
BACKEND_MODEL_NAME = os.getenv("COSYVOICE_BACKEND_MODEL_NAME", "cosyvoice3")
BACKEND_TIMEOUT_SECONDS = env_float("COSYVOICE_BACKEND_TIMEOUT_SECONDS", 120.0)
BACKEND_SEGMENT_WORKERS = env_int("COSYVOICE_BACKEND_SEGMENT_WORKERS", 1)
TTS_CONCURRENCY_LIMIT = env_int("COSYVOICE_TTS_CONCURRENCY_LIMIT", 32)
