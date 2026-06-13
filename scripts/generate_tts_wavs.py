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
    default_root = Path.home() / "Documents" / "OpenJTalk" / "x64" / "Debug"
    default_project = Path.home() / "Documents" / "OpenJTalk"
    default_data = default_project / "OpenJTalk"

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("tts/input.txt"))
    parser.add_argument("--output-dir", type=Path, default=Path("tts/generated"))
    parser.add_argument("--open-jtalk", type=Path, default=default_root / "OpenJTalk.exe")
    parser.add_argument("--hts-engine", type=Path, default=default_root / "hts_engine_cli.exe")
    parser.add_argument("--raw-engine", type=Path, default=default_root / "hts_engine_raw_cli.exe")
    parser.add_argument("--dic", type=Path, default=default_data / "open_jtalk_dic_utf_8-1.11")
    parser.add_argument("--voice", type=Path, default=default_data / "mei" / "mei_normal.htsvoice")
    args = parser.parse_args()

    for path in (args.open_jtalk, args.hts_engine, args.raw_engine, args.voice, args.dic, args.input):
        if not path.exists():
            raise RuntimeError(f"Missing required path: {path}")

    phrases = read_phrases(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_name:
        temp_dir = Path(temp_name)
        raw_voice = temp_dir / "voice_16k.raw"
        subprocess.run(
            [
                str(args.hts_engine),
                "export-voice",
                "--voice", str(args.voice),
                "--output", str(raw_voice),
                "--tts-16khz",
            ],
            check=True,
        )
        generated: list[Path] = []
        for index, phrase in enumerate(phrases):
            text_path = temp_dir / f"phrase_{index:03d}.txt"
            wav_path = args.output_dir / f"phrase_{index:03d}.wav"
            text_path.write_text(phrase + "\n", encoding="utf-8")
            subprocess.run(
                [
                    str(args.open_jtalk),
                    "-x", str(args.dic),
                    "-raw", str(raw_voice),
                    "-raw-engine", str(args.raw_engine),
                    "-raw-block-frames", "256",
                    "-ow", str(wav_path),
                    str(text_path),
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
