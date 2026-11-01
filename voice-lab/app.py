import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = Path(os.getenv("ORAK_VOICE_MODELS", BASE_DIR / "models"))
REGISTRY_FILE = BASE_DIR / "voices.json"

app = FastAPI(
    title="ORAK Voice Lab API",
    description="Private multi-speaker Arabic TTS service for ORAK AI.",
    version="0.1.0",
)


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


@app.get("/health")
def health():
    return {"service": "ORAK Voice Lab", "status": "ready", "stage": "foundation"}


@app.get("/voices")
def voices():
    result = []
    for voice in load_registry():
        model_path = MODEL_DIR / voice["model_file"]
        config_path = Path(str(model_path) + ".json")
        result.append({
            **voice,
            "available": model_path.is_file() and config_path.is_file(),
        })
    return {"voices": result}


@app.post("/synthesize")
def synthesize(request: SynthesisRequest):
    voice = find_voice(request.voice_id)
    model_path = (MODEL_DIR / voice["model_file"]).resolve()
    expected_parent = MODEL_DIR.resolve()
    if expected_parent not in model_path.parents:
        raise HTTPException(status_code=400, detail="Invalid model path")

    config_path = Path(str(model_path) + ".json")
    if not model_path.is_file() or not config_path.is_file():
        raise HTTPException(
            status_code=503,
            detail="This ORAK voice has not been trained/exported yet."
        )

    # Piper CLI reads text from stdin and writes a WAV file.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as output:
        output_path = Path(output.name)

    try:
        completed = subprocess.run(
            [
                "piper",
                "--model", str(model_path),
                "--config", str(config_path),
                "--output_file", str(output_path),
            ],
            input=request.text,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0 or not output_path.exists():
            raise HTTPException(status_code=500, detail="Voice synthesis failed; check Piper runtime/model.")
        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename=f"{request.voice_id}.wav",
            background=None,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Piper CLI is not installed on this machine.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Synthesis timed out.") from exc
