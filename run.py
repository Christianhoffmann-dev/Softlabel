"""SoftLabel Startpunkt — auch lokal ohne Docker nutzbar:  python run.py"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("SL_HOST", "0.0.0.0"),
        port=int(os.environ.get("SL_PORT", "8000")),
        # Für viele gleichzeitige Nutzer: 2–4 Worker empfehlen (CPU-Exporte).
        workers=int(os.environ.get("SL_WORKERS", "1")),
    )
