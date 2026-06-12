#!/usr/bin/env python3
"""Print simple quality metrics for 16-bit mono WAV files."""

import argparse
import math
import wave
from array import array
from pathlib import Path


def inspect_wav(path: Path) -> None:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()
        pcm = wav.readframes(frames)

    if channels != 1 or sample_width != 2:
        print(f"{path}: unsupported format channels={channels} sample_width={sample_width}")
        return

    samples = array("h")
    samples.frombytes(pcm)
    if not samples:
        print(f"{path}: empty")
        return

    peak = max(abs(sample) for sample in samples)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    clipped = sum(1 for sample in samples if sample <= -32768 or sample >= 32767)
    clipped_percent = clipped * 100.0 / len(samples)
    duration = frames / sample_rate

    print(
        f"{path}: duration={duration:.2f}s rate={sample_rate}Hz "
        f"peak={peak} rms={rms:.1f} clipped={clipped_percent:.3f}%"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="WAV files or directories")
    args = parser.parse_args()

    for raw_path in args.paths:
        path = Path(raw_path)
        if path.is_dir():
            for wav_path in sorted(path.rglob("*.wav")):
                inspect_wav(wav_path)
        else:
            inspect_wav(path)


if __name__ == "__main__":
    main()
