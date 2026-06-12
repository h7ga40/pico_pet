#!/usr/bin/env python3
"""Check the Python Log-Mel implementation against generated C golden data."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from generate_speech_feature_test_data import make_test_pcm
from speech_features import log_mel_frame


def parse_float_array(header_text: str, symbol: str) -> np.ndarray:
    pattern = rf"{symbol}\[[^\]]+\]\s*=\s*\{{(?P<body>.*?)\}};"
    match = re.search(pattern, header_text, flags=re.DOTALL)
    if not match:
        raise RuntimeError(f"Could not find {symbol}")
    values = re.findall(r"[-+]?\d+\.\d+e[-+]?\d+f", match.group("body"), flags=re.IGNORECASE)
    return np.array([float(value[:-1]) for value in values], dtype=np.float32)


def main() -> None:
    header_path = Path("include/speech_features_test_data.h")
    expected = parse_float_array(header_path.read_text(encoding="utf-8"), "k_speech_feature_test_log_mel")
    actual = log_mel_frame(make_test_pcm())
    max_abs_error = float(np.max(np.abs(actual - expected)))
    print(f"max_abs_error={max_abs_error:.9e}")
    if max_abs_error > 1.0e-6:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
