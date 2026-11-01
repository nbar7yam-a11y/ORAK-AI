import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = Path(os.getenv("ORAK_VOICE_MODELS", BASE_DIR / "models"))
REGISTRY_FILE = BASE_DIR / "voices.json"
MAX_AUDIO_BYTES = 50 * 1024 * 1024
ALLOWED_TYPES = {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/mp4", "audio/x-m4a", "audio/aac", "audio/ogg", "audio/flac"}

app = FastAPI(title="ORAK Voice Lab API", description="Private voice library and Arabic TTS service for ORAK AI.", version="0.2.0")


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
        raise HTTPException(status_code=503, detail="Upload security is not configured on the server.")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid ORAK upload key.")


def r2_client():
    account_id = os.getenv("R2_ACCOUNT_ID")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET_NAME")
    if not all((account_id, access_key, secret_key, bucket)):
        raise HTTPException(status_code=503, detail="Cloud storage is not configured yet.")
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )
    return client, bucket


@app.get("/health")
def health():
    return {"service": "ORAK Voice Lab", "status": "ready", "stage": "voice-library"}


@app.get("/voices")
def voices():
    result = []
    for voice in load_registry():
        model_path = MODEL_DIR / voice["model_file"]
        config_path = Path(str(model_path) + ".json")
        result.append({**voice, "available": model_path.is_file() and config_path.is_file()})
    return {"voices": result}


@app.post("/library/upload")
async def upload_audio(
    file: UploadFile = File(...),
    voice_name: str = Form(...),
    voice_type: str = Form("other"),
    language: str = Form("ar"),
    authorization: str | None = Header(default=None),
):
    require_upload_token(authorization)
    if not voice_name.strip() or len(voice_name) > 80:
        raise HTTPException(status_code=400, detail="Enter a voice name up to 80 characters.")
    if voice_type not in {"female", "male", "other"}:
        raise HTTPException(status_code=400, detail="Invalid voice type.")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Use WAV, MP3, M4A, AAC, OGG or FLAC audio.")
    data = await file.read(MAX_AUDIO_BYTES + 1)
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio must be between 1 byte and 50 MB.")
    suffix = Path(file.filename or "audio.wav").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}:
        suffix = ".audio"
    object_key = f"library/{uuid.uuid4().hex}{suffix}"
    client, bucket = r2_client()
    client.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=data,
        ContentType=content_type,
        Metadata={
            "voice-name": voice_name.strip(),
            "voice-type": voice_type,
            "language": language[:12],
            "original-filename": Path(file.filename or "audio").name[:120],
            "uploaded-at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"ok": True, "key": object_key, "name": voice_name.strip(), "size": len(data)}


@app.get("/library")
def list_library(authorization: str | None = Header(default=None)):
    require_upload_token(authorization)
    client, bucket = r2_client()
    response = client.list_objects_v2(Bucket=bucket, Prefix="library/")
    items = []
    for obj in response.get("Contents", []):
        head = client.head_object(Bucket=bucket, Key=obj["Key"])
        meta = head.get("Metadata", {})
        items.append({
            "key": obj["Key"],
            "name": meta.get("voice-name", "صوت بدون اسم"),
            "type": meta.get("voice-type", "other"),
            "language": meta.get("language", "ar"),
            "size": obj["Size"],
            "uploaded_at": meta.get("uploaded-at"),
            "play_url": client.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": obj["Key"]}, ExpiresIn=900
            ),
        })
    items.sort(key=lambda item: item.get("uploaded_at") or "", reverse=True)
    return {"items": items}


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
        completed = subprocess.run(
            ["piper", "--model", str(model_path), "--config", str(config_path), "--output_file", str(output_path)],
            input=request.text, text=True, capture_output=True, timeout=120, check=False,
        )
        if completed.returncode != 0 or not output_path.exists():
            raise HTTPException(status_code=500, detail="Voice synthesis failed; check Piper runtime/model.")
        return FileResponse(output_path, media_type="audio/wav", filename=f"{request.voice_id}.wav")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Piper CLI is not installed on this machine.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Synthesis timed out.") from exc
