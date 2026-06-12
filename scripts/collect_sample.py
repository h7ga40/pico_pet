#!/usr/bin/env python3
"""Collect labeled PicoWakeup WAV samples with predictable filenames."""

import argparse
import subprocess
import sys
from pathlib import Path


VALID_LABELS = ("positive", "negative", "near_miss")


def next_sample_path(root: Path, label: str, prefix: str) -> Path:
    label_dir = root / label
    label_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(label_dir.glob(f"{prefix}_*.wav"))
    if not existing:
        return label_dir / f"{prefix}_001.wav"

    max_index = 0
    for path in existing:
        stem = path.stem
        try:
            max_index = max(max_index, int(stem.rsplit("_", 1)[1]))
        except (IndexError, ValueError):
            continue

    return label_dir / f"{prefix}_{max_index + 1:03d}.wav"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", help="Serial port, for example COM3")
    parser.add_argument("label", choices=VALID_LABELS)
    parser.add_argument("--root", default="samples", help="Dataset output root")
    parser.add_argument("--seconds", type=int, default=5)
    parser.add_argument("--prefix", default=None)
    args = parser.parse_args()

    root = Path(args.root)
    prefix = args.prefix if args.prefix else args.label
    output_path = next_sample_path(root, args.label, prefix)

    print(f"Recording {args.label}: {output_path}")
    command = [
        sys.executable,
        str(Path(__file__).with_name("record_wav.py")),
        args.port,
        str(output_path),
        "--seconds",
        str(args.seconds),
    ]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
