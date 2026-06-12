#!/usr/bin/env python3
"""Generate C golden data for speech_features_self_test()."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from speech_features import FRAME_LENGTH, MEL_BINS, log_mel_frame


def format_int16_array(values: np.ndarray, columns: int = 10) -> str:
    lines: list[str] = []
    for offset in range(0, len(values), columns):
        chunk = values[offset:offset + columns]
        lines.append("    " + ", ".join(str(int(value)) for value in chunk) + ",")
    return "\n".join(lines)


def format_float_array(values: np.ndarray, columns: int = 5) -> str:
    lines: list[str] = []
    for offset in range(0, len(values), columns):
        chunk = values[offset:offset + columns]
        lines.append("    " + ", ".join(f"{float(value):.9e}f" for value in chunk) + ",")
    return "\n".join(lines)


def make_test_pcm() -> np.ndarray:
    samples = []
    for n in range(FRAME_LENGTH):
        tone_a = 9000.0 * math.sin(2.0 * math.pi * 440.0 * n / 16000.0)
        tone_b = 3000.0 * math.sin(2.0 * math.pi * 1700.0 * n / 16000.0)
        chirp = 1200.0 * math.sin(2.0 * math.pi * (100.0 + n * 2.0) * n / 16000.0)
        samples.append(round(tone_a + tone_b + chirp))
    return np.array(samples, dtype=np.int16)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="include/speech_features_test_data.h")
    args = parser.parse_args()

    pcm = make_test_pcm()
    expected = log_mel_frame(pcm)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    guard = output_path.name.upper().replace(".", "_")
    output_path.write_text(
        "\n".join(
            [
                f"#ifndef {guard}",
                f"#define {guard}",
                "",
                "#include <stdint.h>",
                "",
                f"#define SPEECH_FEATURE_TEST_FRAME_LENGTH {FRAME_LENGTH}",
                f"#define SPEECH_FEATURE_TEST_MEL_BINS {MEL_BINS}",
                "",
                "static const int16_t k_speech_feature_test_pcm[SPEECH_FEATURE_TEST_FRAME_LENGTH] = {",
                format_int16_array(pcm),
                "};",
                "",
                "static const float k_speech_feature_test_log_mel[SPEECH_FEATURE_TEST_MEL_BINS] = {",
                format_float_array(expected),
                "};",
                "",
                f"#endif  // {guard}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
