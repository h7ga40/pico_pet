#!/usr/bin/env python3
"""Run a trained Keras keyword-spotting model on WAV files."""

import argparse
import json
import wave
from pathlib import Path

import numpy as np
import tensorflow as tf

from train_kws import LogMelSpectrogram, SAMPLE_COUNT, SAMPLE_RATE


def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()
        pcm = wav.readframes(frames)

    if channels != 1 or sample_width != 2 or sample_rate != SAMPLE_RATE:
        raise ValueError(f"{path} must be 16 kHz, 16-bit, mono WAV")

    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.shape[0] < SAMPLE_COUNT:
        audio = np.pad(audio, (0, SAMPLE_COUNT - audio.shape[0]))
    elif audio.shape[0] > SAMPLE_COUNT:
        audio = audio[:SAMPLE_COUNT]
    return audio


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/kws/model.keras")
    parser.add_argument("--labels", default="models/kws/labels.json")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    model = tf.keras.models.load_model(
        args.model,
        custom_objects={"LogMelSpectrogram": LogMelSpectrogram},
    )
    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))["labels"]

    wav_paths: list[Path] = []
    for raw_path in args.paths:
        path = Path(raw_path)
        if path.is_dir():
            wav_paths.extend(sorted(path.rglob("*.wav")))
        else:
            wav_paths.append(path)

    for path in wav_paths:
        audio = load_wav(path)
        scores = model.predict(audio[np.newaxis, :], verbose=0)[0]
        best_index = int(np.argmax(scores))
        score_text = " ".join(f"{label}={scores[i]:.3f}" for i, label in enumerate(labels))
        print(f"{path}: predicted={labels[best_index]} {score_text}")


if __name__ == "__main__":
    main()
