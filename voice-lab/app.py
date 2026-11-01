import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = Path(os.getenv("ORAK_VOICE_MODELS", BASE_DIR / "models"))
DATA_DIR = Path(os.getenv("ORAK_VOICE_DATA", BASE_DIR / "data"))
AUDIO_DIR = DATA_DIR / "library"
INDEX_FILE = DATA_DIR / "library.json"
REGISTRY_FILE = BASE_DIR / "voices.json"
MAX_AUDIO_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}

app = FastAPI(title="ORAK Voice Lab API", description="Private self-hosted voice library for ORAK AI.", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])


class SynthesisRequest(BaseModel):
    voice_id: str = Field(min_length=3, max_length=64)
    text: str = Field(min_length=1, max_length=2000)


def load_registry():
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))["voices"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(status_code=500, detail="Voice registry is unavailable") from exc


def find_voice(voice_id: str):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", voice_id):
        raise HTTPException(status_code=400, detail="Invalid voice_id")
    for voice in load_registry():
        if voice["voice_id"] == voice_id:
            return voice
    raise HTTPException(status_code=404, detail="Voice not found")


def require_upload_token(authorization: str | None):
    expected = os.getenv("ORAK_UPLOAD_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Server security is not configured.")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid ORAK upload key.")


def read_library():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        return []
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Voice library index is damaged.") from exc


def write_library(items):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_index = INDEX_FILE.with_suffix(".tmp")
    temp_index.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_index.replace(INDEX_FILE)


@app.get("/")
def home():
    page = BASE_DIR / "index.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="Voice Studio page is missing.")
    return FileResponse(page, media_type="text/html")


@app.get("/health")
def health():
    return {"service": "ORAK Voice Lab", "status": "ready", "stage": "self-hosted-library"}


@app.get("/voices")
def voices():
    result = []
    for voice in load_registry():
        model_path = MODEL_DIR / voice["model_file"]
        config_path = Path(str(model_path) + ".json")
        result.append({**voice, "available": model_path.is_file() and config_path.is_file()})
    return {"voices": result}


@app.post("/library/upload")
async def upload_audio(file: UploadFile = File(...), voice_name: str = Form(...), voice_type: str = Form("other"), language: str = Form("ar"), authorization: str | None = Header(default=None)):
    require_upload_token(authorization)
    if not voice_name.strip() or len(voice_name) > 80:
        raise HTTPException(status_code=400, detail="Enter a voice name up to 80 characters.")
    if voice_type not in {"female", "male", "other"}:
        raise HTTPException(status_code=400, detail="Invalid voice type.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Use WAV, MP3, M4A, AAC, OGG or FLAC audio.")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    object_name = f"{uuid.uuid4().hex}{suffix}"
    destination = AUDIO_DIR / object_name
    total = 0
    try:
        with destination.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_AUDIO_BYTES:
                    raise HTTPException(status_code=413, detail="Audio must be 50 MB or smaller.")
                output.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="The selected audio file is empty.")
        item = {"key": object_name, "name": voice_name.strip(), "type": voice_type, "language": language[:12], "size": total, "uploaded_at": datetime.now(timezone.utc).isoformat()}
        items = read_library()
        items.append(item)
        write_library(items)
        return {"ok": True, **item}
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@app.get("/library")
def list_library(authorization: str | None = Header(default=None)):
    require_upload_token(authorization)
    result = []
    for item in sorted(read_library(), key=lambda value: value.get("uploaded_at", ""), reverse=True):
        if (AUDIO_DIR / item["key"]).is_file():
            result.append({**item, "play_url": f"/library/{item['key']}/play"})
    return {"items": result}


@app.get("/library/{key}/play")
def play_audio(key: str, authorization: str | None = Header(default=None)):
    require_upload_token(authorization)
    if not re.fullmatch(r"[a-f0-9]{32}\.(wav|mp3|m4a|aac|ogg|flac)", key):
        raise HTTPException(status_code=400, detail="Invalid audio key.")
    path = AUDIO_DIR / key
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found.")
    media = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg", ".flac": "audio/flac"}[path.suffix]
    return FileResponse(path, media_type=media, filename=key)


@app.post("/synthesize")
def synthesize(request: SynthesisRequest):
    voice = find_voice(request.voice_id)
    model_path = (MODEL_DIR / voice["model_file"]).resolve()
    if MODEL_DIR.resolve() not in model_path.parents:
        raise HTTPException(status_code=400, detail="Invalid model path")
    config_path = Path(str(model_path) + ".json")
    if not model_path.is_file() or not config_path.is_file():
        raise HTTPException(status_code=503, detail="This ORAK voice has not been trained/exported yet.")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as output:
        output_path = Path(output.name)
    try:
        completed = subprocess.run(["piper", "--model", str(model_path), "--config", str(config_path), "--output_file", str(output_path)], input=request.text, text=True, capture_output=True, timeout=120, check=False)
        if completed.returncode != 0 or not output_path.exists():
            raise HTTPException(status_code=500, detail="Voice synthesis failed; check Piper runtime/model.")
        return FileResponse(output_path, media_type="audio/wav", filename=f"{request.voice_id}.wav")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Piper CLI is not installed on this machine.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Synthesis timed out.") from exc
