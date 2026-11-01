# ORAK Voice Lab

Private voice research and synthesis workspace for ORAK AI.

## Current milestone: foundation
This repository contains the initial service scaffold and dataset preparation tools. It does **not** yet contain trained ORAK voices or a proprietary neural model.

## Architecture
- Capture: record speakers only with explicit informed consent.
- Dataset: one clean WAV utterance per line, paired with an exact transcript and speaker ID.
- Training: train/fine-tune a multi-speaker TTS model in a GPU environment.
- Runtime: serve only approved, locally stored voice models through the ORAK API.
- Library: version model weights, metadata, language, license, and consent provenance.

## Important model/licensing decision
The first prototype uses Piper-compatible model packaging as a lightweight local runtime target. Piper's training workflow supports preparing datasets, training/fine-tuning, and exporting ONNX models. Verify the current Piper code and each checkpoint's license before using it. Do not assume every downloaded voice or checkpoint permits commercial redistribution.

XTTS-v2 supports Arabic and voice/style conditioning, but its model is under the Coqui Public Model License. Review that license carefully before commercial use; this project does not bundle XTTS weights.

## Dataset format
Create a directory like:

```
data/
  speaker_f01/
    wav/
      000001.wav
      000002.wav
    metadata.csv
  speaker_m01/
    wav/
      000001.wav
    metadata.csv
```

Each `metadata.csv` row:
```
filename|transcript
000001|مرحباً، أنا صوت تجريبي من مختبر أوراك.
```

Recording guidance:
- Use a quiet room and the same microphone position.
- Record uncompressed mono WAV; keep levels consistent and avoid clipping.
- Keep each clip to one sentence, with exact punctuation/transcript.
- Collect balanced neutral, question, happy, sad, calm, and emphatic examples.
- Aim initially for 30–60 minutes per speaker for a small experiment; natural, robust voices generally need substantially more varied, carefully transcribed data.
- Obtain written permission from every speaker. Never clone a person without consent.

## Local setup
Requires a computer with Python 3.10+; GPU is strongly recommended for training. An Android phone can record source audio and manage GitHub, but it is not a practical full model-training machine.

```bash
cd voice-lab
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# Linux/macOS:
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000/docs`.

## Runtime model placement
After training/exporting a Piper-compatible ONNX model, place approved files here:

```
voice-lab/models/
  orak_female_01.onnx
  orak_female_01.onnx.json
  orak_male_01.onnx
  orak_male_01.onnx.json
```

Set `ORAK_VOICE_MODELS` to the models directory if it is elsewhere. The API only exposes models listed in `voices.json`.

## Cloud + local workflow
- GitHub stores source code and metadata, not large raw recordings or model weights.
- Use a GPU notebook/cloud machine for training; export the model artifact.
- Download the approved artifact to a computer for local, offline inference.
- Cloudflare Workers can host the web control plane, but should not run PyTorch model training. Keep inference on a separate Python model service or local machine.

## API
- `GET /health`
- `GET /voices`
- `POST /synthesize` with JSON: `{"voice_id":"orak_female_01","text":"مرحباً بك في أوراك" }`

The synthesis route is enabled only when the selected model files and Piper runtime are installed.
