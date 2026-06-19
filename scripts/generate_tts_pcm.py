#!/usr/bin/env python3
"""Convert 16 kHz mono WAV files into an embedded PCM phrase table."""

import argparse
import struct
import wave
from pathlib import Path


TARGET_SAMPLE_RATE = 16000
TARGET_SAMPLE_WIDTH = 2
TARGET_CHANNELS = 1


def c_samples(data: bytes, columns: int = 12) -> str:
    samples = struct.unpack(f"<{len(data) // 2}h", data)
    lines = []
    for offset in range(0, len(samples), columns):
        chunk = samples[offset:offset + columns]
        lines.append("    " + ", ".join(str(value) for value in chunk) + ",")
    return "\n".join(lines)


def decode_pcm(pcm: bytes, sample_width: int) -> list[int]:
    if sample_width == 1:
        return [(value - 128) << 8 for value in pcm]
    if sample_width == 2:
        return list(struct.unpack(f"<{len(pcm) // 2}h", pcm))
    if sample_width == 3:
        samples = []
        for offset in range(0, len(pcm), 3):
            value = pcm[offset] | (pcm[offset + 1] << 8) | (pcm[offset + 2] << 16)
            if value & 0x800000:
                value -= 0x1000000
            samples.append(max(-32768, min(32767, value >> 8)))
        return samples
    if sample_width == 4:
        values = struct.unpack(f"<{len(pcm) // 4}i", pcm)
        return [max(-32768, min(32767, value >> 16)) for value in values]
    raise RuntimeError(f"unsupported sample width: {sample_width}")


def mono_samples(samples: list[int], channels: int) -> list[int]:
    if channels == 1:
        return samples
    output = []
    for offset in range(0, len(samples), channels):
        frame = samples[offset:offset + channels]
        output.append(int(sum(frame) / len(frame)))
    return output


def resample_linear(samples: list[int], source_rate: int) -> list[int]:
    if source_rate == TARGET_SAMPLE_RATE:
        return samples
    if not samples:
        return []

    output_length = max(1, round(len(samples) * TARGET_SAMPLE_RATE / source_rate))
    output = []
    for index in range(output_length):
        source_position = index * source_rate / TARGET_SAMPLE_RATE
        left = int(source_position)
        right = min(left + 1, len(samples) - 1)
        fraction = source_position - left
        value = samples[left] * (1.0 - fraction) + samples[right] * fraction
        output.append(int(round(max(-32768, min(32767, value)))))
    return output


def encode_pcm16(samples: list[int]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def wav_to_pcm16_mono_16k(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frame_count = wav.getnframes()
        pcm = wav.readframes(frame_count)

    if channels < 1:
        raise RuntimeError(f"{path} has no audio channels")
    if sample_width not in (1, 2, 3, 4):
        raise RuntimeError(f"{path} has unsupported sample width: {sample_width}")

    samples = decode_pcm(pcm, sample_width)
    samples = mono_samples(samples, channels)
    samples = resample_linear(samples, sample_rate)
    return encode_pcm16(samples)


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(TARGET_CHANNELS)
        wav.setsampwidth(TARGET_SAMPLE_WIDTH)
        wav.setframerate(TARGET_SAMPLE_RATE)
        wav.writeframes(pcm)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", type=Path, action="append", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--normalized-dir", type=Path)
    args = parser.parse_args()

    pcm_files: list[bytes] = []
    for index, wav_path in enumerate(args.wav):
        pcm = wav_to_pcm16_mono_16k(wav_path)
        pcm_files.append(pcm)
        if args.normalized_dir is not None:
            write_wav(args.normalized_dir / f"phrase_{index:03d}.wav", pcm)

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
