#!/usr/bin/env python3
"""Convert 16 kHz mono WAV files into an embedded PCM phrase table."""

import argparse
import struct
import wave
from pathlib import Path


def c_samples(data: bytes, columns: int = 12) -> str:
    samples = struct.unpack(f"<{len(data) // 2}h", data)
    lines = []
    for offset in range(0, len(samples), columns):
        chunk = samples[offset:offset + columns]
        lines.append("    " + ", ".join(str(value) for value in chunk) + ",")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", type=Path, action="append", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--header", type=Path, required=True)
    args = parser.parse_args()

    pcm_files: list[bytes] = []
    for wav_path in args.wav:
        with wave.open(str(wav_path), "rb") as wav:
            sample_rate = wav.getframerate()
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                raise RuntimeError(f"{wav_path} must be 16-bit mono")
            if sample_rate != 16000:
                raise RuntimeError(f"{wav_path} must be 16 kHz, got {sample_rate} Hz")
            pcm_files.append(wav.readframes(wav.getnframes()))

    args.source.parent.mkdir(parents=True, exist_ok=True)
    args.header.parent.mkdir(parents=True, exist_ok=True)
    guard = args.header.name.upper().replace(".", "_").replace("-", "_")
    args.header.write_text(
        f"#ifndef {guard}\n#define {guard}\n\n#include <stddef.h>\n#include <stdint.h>\n\n"
        "typedef struct {\n"
        "    const int16_t *samples;\n"
        "    size_t sample_count;\n"
        "} tts_pcm_phrase_t;\n\n"
        "extern const tts_pcm_phrase_t g_tts_pcm_phrases[];\n"
        "extern const size_t g_tts_pcm_phrase_count;\n\n#endif\n",
        encoding="utf-8",
    )
    source_lines = [f'#include "{args.header.name}"', ""]
    for index, pcm in enumerate(pcm_files):
        source_lines.extend(
            [
                f"static const int16_t phrase_{index:03d}[] __attribute__((aligned(4))) = {{",
                c_samples(pcm),
                "};",
                "",
            ]
        )
    source_lines.append("const tts_pcm_phrase_t g_tts_pcm_phrases[] = {")
    for index in range(len(pcm_files)):
        source_lines.append(
            f"    {{ phrase_{index:03d}, sizeof(phrase_{index:03d}) / sizeof(phrase_{index:03d}[0]) }},"
        )
    source_lines.extend(
        [
            "};",
            "",
            "const size_t g_tts_pcm_phrase_count = sizeof(g_tts_pcm_phrases) / sizeof(g_tts_pcm_phrases[0]);",
            "",
        ]
    )
    args.source.write_text("\n".join(source_lines), encoding="utf-8")
    print(f"generated {len(pcm_files)} phrases at 16000 Hz")


if __name__ == "__main__":
    main()
