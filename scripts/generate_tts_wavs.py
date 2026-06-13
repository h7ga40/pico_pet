#!/usr/bin/env python3
"""Generate one 16 kHz WAV per non-empty line in a UTF-8 input file."""

import argparse
import subprocess
import tempfile
import wave
from pathlib import Path


def read_phrases(path: Path) -> list[str]:
    phrases = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            phrases.append(text)
    if not phrases:
        raise RuntimeError(f"No phrases found in {path}")
    return phrases


def validate_wav(path: Path) -> None:
    with wave.open(str(path), "rb") as wav:
        if wav.getframerate() != 16000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise RuntimeError(f"{path} must be 16 kHz, 16-bit, mono")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    default_data = repo_root / "tools" / "openjtalk"

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("tts/input.txt"))
    parser.add_argument("--output-dir", type=Path, default=Path("tts/generated"))
    parser.add_argument("--open-jtalk", type=Path, default=repo_root / "tools" / "openjtalk" / "OpenJTalk.exe")
    parser.add_argument("--dic", type=Path, default=default_data / "open_jtalk_dic_utf_8-1.11")
    parser.add_argument("--voice", type=Path, default=default_data / "mei" / "mei_normal.htsvoice")
    args = parser.parse_args()

    for path in (args.open_jtalk, args.voice, args.dic, args.input):
        if not path.exists():
            raise RuntimeError(f"Missing required path: {path}")

    phrases = read_phrases(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_name:
        temp_dir = Path(temp_name)
        generated: list[Path] = []
        for index, phrase in enumerate(phrases):
            text_path = temp_dir / f"phrase_{index:03d}.txt"
            wav_path = args.output_dir / f"phrase_{index:03d}.wav"
            text_path.write_text(phrase + "\n", encoding="utf-8")
            subprocess.run(
                [
                    str(args.open_jtalk),
                    "--dic", str(args.dic),
                    "--voice", str(args.voice),
                    "--sample-rate", "16000",
                    "--input", str(text_path),
                    "--output", str(wav_path),
                ],
                check=True,
            )
            validate_wav(wav_path)
            generated.append(wav_path)
            print(f"{wav_path}: {phrase}")

    generated_names = {path.name for path in generated}
    for stale_path in args.output_dir.glob("phrase_*.wav"):
        if stale_path.name not in generated_names:
            stale_path.unlink()


if __name__ == "__main__":
    main()
