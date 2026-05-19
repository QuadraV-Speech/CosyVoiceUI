
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .api.enroll import router as enroll_router
from .api.tts import router as tts_router
from .config import WEB_DIR, SERVER_PORT, USE_SSL, SSL_CERT, SSL_KEY
from pathlib import Path

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



@app.get("/")
def index():
    return FileResponse(Path(WEB_DIR) / "index.html")


app.include_router(enroll_router)
app.include_router(tts_router)


if __name__ == "__main__":

    if USE_SSL:
        uvicorn.run(
            "CosyVoiceUI.server:app",
            host="0.0.0.0",
            port=SERVER_PORT,
            ssl_certfile=SSL_CERT,
            ssl_keyfile=SSL_KEY,
        )
    else:
        uvicorn.run(
            "CosyVoiceUI.server:app",
            host="0.0.0.0",
            port=SERVER_PORT,
            reload=True,
        )