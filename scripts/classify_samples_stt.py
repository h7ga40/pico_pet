#!/usr/bin/env python3
"""Classify WAV clips from samples/unclassified using local STT."""

import argparse
import csv
import re
import shutil
import unicodedata
import wave
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

from collect_sample import next_sample_path


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", "", text)


def filename_prefix(text: str, max_length: int = 40) -> str:
    """Return a short Windows-safe filename prefix from an STT transcript."""
    text = unicodedata.normalize("NFKC", text).strip()
    text = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip(" ._")
    text = text[:max_length].rstrip(" ._") or "speech"

    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"COM{number}" for number in range(1, 10))
    reserved.update(f"LPT{number}" for number in range(1, 10))
    if text.upper() in reserved:
        text = f"speech_{text}"
    return text


def classify_text(text: str, target: str, near_threshold: float) -> tuple[str, float]:
    normalized = normalize_text(text)
    target_normalized = normalize_text(target)
    if not target_normalized:
        raise ValueError("Wake phrase is empty after text normalization")
    if target_normalized in normalized:
        return "positive", 1.0
    similarity = SequenceMatcher(None, normalized, target_normalized).ratio()
    if similarity >= near_threshold:
        return "near_miss", similarity
    return "negative", similarity


def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        if wav.getframerate() != 16000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError(f"{path} must be 16 kHz, 16-bit, mono")
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768.0


def append_metadata(path: Path, row: list[str]) -> None:
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        if new_file:
            writer.writerow(["source", "path", "label", "transcript", "similarity"])
        writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Wake phrase used for automatic classification")
    parser.add_argument("--root", type=Path, default=Path("samples"))
    parser.add_argument("--model", default="small", help="faster-whisper model name or path")
    parser.add_argument("--language", default="ja")
    parser.add_argument("--near-threshold", type=float, default=0.45)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args()

    if not normalize_text(args.target):
        parser.error("target must contain letters, digits, kana, or kanji")
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise SystemExit("Install STT dependencies: pip install -r requirements-stt.txt") from error

    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    source_dir = args.root / "unclassified"
    metadata_path = args.root / "metadata.csv"
    paths = sorted(source_dir.glob("*.wav"))
    if not paths:
        print(f"No WAV files found in {source_dir}")
        return

    for source in paths:
        segments, _ = model.transcribe(
            load_wav(source),
            language=args.language,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        transcript = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        if not transcript:
            print(f"{source}: no speech recognized; left unclassified")
            continue
        label, similarity = classify_text(transcript, args.target, args.near_threshold)
        destination = next_sample_path(args.root, label, filename_prefix(transcript))
        shutil.move(str(source), destination)
        append_metadata(
            metadata_path,
            [str(source), str(destination), label, transcript, f"{similarity:.3f}"],
        )
        print(f"{destination}: {label} similarity={similarity:.3f} text={transcript!r}")


if __name__ == "__main__":
    main()
