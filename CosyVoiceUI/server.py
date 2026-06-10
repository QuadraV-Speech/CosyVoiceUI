
import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .api.enroll import router as enroll_router
from .api.tts import router as tts_router
from .config import ACCESS_LOG, ENABLE_RELOAD, LOG_LEVEL, WEB_DIR, SERVER_PORT, USE_SSL, SSL_CERT, SSL_KEY
from .logging_config import new_request_id, reset_request_id, set_request_id, setup_logging
from pathlib import Path

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CosyVoice 后台管理 API",
    description="",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or new_request_id()
    token = set_request_id(request_id)
    start_time = time.perf_counter()

    try:
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "request failed method=%s path=%s client=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                request.client.host if request.client else "-",
                duration_ms,
            )
            raise

        response.headers["X-Request-ID"] = request_id

        if ACCESS_LOG:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "request completed method=%s path=%s status=%s client=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                response.status_code,
                request.client.host if request.client else "-",
                duration_ms,
            )

        return response
    finally:
        reset_request_id(token)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled exception path=%s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error"},
    )



@app.get("/")
def index():
    return FileResponse(Path(WEB_DIR) / "index.html")


app.include_router(enroll_router)
app.include_router(tts_router)


if __name__ == "__main__":
    import uvicorn

    logger.info("starting CosyVoiceUI server port=%s ssl=%s reload=%s", SERVER_PORT, USE_SSL, ENABLE_RELOAD)

    if USE_SSL:
        uvicorn.run(
            "CosyVoiceUI.server:app",
            host="0.0.0.0",
            port=SERVER_PORT,
            ssl_certfile=SSL_CERT,
            ssl_keyfile=SSL_KEY,
            log_level=LOG_LEVEL.lower(),
            access_log=False,
            reload=ENABLE_RELOAD,
        )
    else:
        uvicorn.run(
            "CosyVoiceUI.server:app",
            host="0.0.0.0",
            port=SERVER_PORT,
            log_level=LOG_LEVEL.lower(),
            access_log=False,
            reload=ENABLE_RELOAD,
        )
