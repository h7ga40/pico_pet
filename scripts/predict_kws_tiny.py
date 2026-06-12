#!/usr/bin/env python3
"""Run a tiny TFLite KWS model on WAV files."""

import argparse
import json
from pathlib import Path

import numpy as np
import tensorflow as tf

from train_kws_tiny import extract_features, load_wav


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/kws_tiny/model_int8.tflite")
    parser.add_argument("--labels", default="models/kws_tiny/labels.json")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))["labels"]
    interpreter = tf.lite.Interpreter(model_path=args.model)
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    input_scale, input_zero_point = input_detail["quantization"]
    output_scale, output_zero_point = output_detail["quantization"]

    wav_paths: list[Path] = []
    for raw_path in args.paths:
        path = Path(raw_path)
        if path.is_dir():
            wav_paths.extend(sorted(path.rglob("*.wav")))
        else:
            wav_paths.append(path)

    for path in wav_paths:
        features = extract_features(load_wav(path))
        quantized = np.round(features / input_scale + input_zero_point)
        quantized = np.clip(quantized, -128, 127).astype(np.int8)
        interpreter.set_tensor(input_detail["index"], quantized[np.newaxis, :])
        interpreter.invoke()
        raw_output = interpreter.get_tensor(output_detail["index"])[0]
        scores = (raw_output.astype(np.float32) - output_zero_point) * output_scale
        best_index = int(np.argmax(scores))
        score_text = " ".join(f"{label}={scores[i]:.3f}" for i, label in enumerate(labels))
        print(f"{path}: predicted={labels[best_index]} {score_text}")


if __name__ == "__main__":
    main()
