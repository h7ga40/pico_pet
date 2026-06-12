#!/usr/bin/env python3
"""Inspect TFLite model size, tensors, and operators."""

import argparse
from pathlib import Path

import tensorflow as tf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    args = parser.parse_args()

    model_path = Path(args.model)
    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    interpreter.allocate_tensors()

    print(f"path={model_path}")
    print(f"size={model_path.stat().st_size} bytes")
    print("inputs:")
    for detail in interpreter.get_input_details():
        print(f"  {detail['name']} shape={detail['shape']} dtype={detail['dtype']}")
        print(f"    quantization={detail['quantization']}")
    print("outputs:")
    for detail in interpreter.get_output_details():
        print(f"  {detail['name']} shape={detail['shape']} dtype={detail['dtype']}")
        print(f"    quantization={detail['quantization']}")
    print("operators:")
    for op in interpreter._get_ops_details():
        print(f"  {op['op_name']}")


if __name__ == "__main__":
    main()
