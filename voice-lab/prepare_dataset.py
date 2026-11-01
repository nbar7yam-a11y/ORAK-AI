"""Validate an ORAK Voice Lab speaker dataset.

Expected:
  speaker_folder/
    metadata.csv   # filename|transcript
    wav/
      000001.wav

This checks structure and transcript presence. It does not assess consent or audio quality.
"""
import argparse
import csv
import wave
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path, help="Path to one speaker folder")
    args = parser.parse_args()

    root = args.dataset
    metadata = root / "metadata.csv"
    wav_dir = root / "wav"
    if not metadata.is_file() or not wav_dir.is_dir():
        raise SystemExit("ERROR: expected metadata.csv and wav/ in the speaker folder")

    errors = []
    count = 0
    with metadata.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter="|")
        for line_no, row in enumerate(reader, start=1):
            if len(row) != 2:
                errors.append(f"line {line_no}: expected filename|transcript")
                continue
            filename, transcript = row
            if not filename.lower().endswith(".wav"):
                filename += ".wav"
            audio_path = wav_dir / filename
            if not transcript.strip():
                errors.append(f"line {line_no}: empty transcript")
            if not audio_path.is_file():
                errors.append(f"line {line_no}: missing {audio_path.name}")
                continue
            try:
                with wave.open(str(audio_path), "rb") as audio:
                    if audio.getnchannels() != 1:
                        errors.append(f"line {line_no}: {filename} is not mono")
                    if audio.getframerate() not in (16000, 22050, 24000):
                        errors.append(f"line {line_no}: {filename} sample rate is {audio.getframerate()} Hz")
                    if audio.getnframes() == 0:
                        errors.append(f"line {line_no}: {filename} is empty")
            except wave.Error:
                errors.append(f"line {line_no}: {filename} is not a readable WAV")
            count += 1

    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print(f"OK: validated {count} WAV entries in {root}")


if __name__ == "__main__":
    main()
