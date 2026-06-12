#!/usr/bin/env python3
"""Export the tiny Dense KWS TFLite model as standalone float C weights."""

import argparse
from pathlib import Path

import numpy as np
import tensorflow as tf


LAYER_SHAPES = ((24, 200), (12, 24), (3, 12))


def dequantize(detail: dict, values: np.ndarray) -> np.ndarray:
    params = detail["quantization_parameters"]
    scales = params["scales"].astype(np.float32)
    zero_points = params["zero_points"].astype(np.float32)
    if scales.size == 1:
        return (values.astype(np.float32) - zero_points[0]) * scales[0]

    shape = [1] * values.ndim
    shape[params["quantized_dimension"]] = scales.size
    return (values.astype(np.float32) - zero_points.reshape(shape)) * scales.reshape(shape)


def format_floats(values: np.ndarray, columns: int = 8) -> str:
    flat = values.reshape(-1)
    lines = []
    for offset in range(0, flat.size, columns):
        chunk = flat[offset:offset + columns]
        formatted = []
        for value in chunk:
            text = f"{float(value):.9g}"
            if "." not in text and "e" not in text:
                text += ".0"
            formatted.append(text + "f")
        lines.append("    " + ", ".join(formatted) + ",")
    return "\n".join(lines)


def format_matrix(values: np.ndarray) -> str:
    rows = []
    for row in values:
        rows.append("    {\n" + format_floats(row) + "\n    },")
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("--source", type=Path, default=Path("src/kws_model_weights.c"))
    parser.add_argument("--header", type=Path, default=Path("include/kws_model_weights.h"))
    args = parser.parse_args()

    interpreter = tf.lite.Interpreter(model_path=str(args.model), experimental_delegates=[])
    interpreter.allocate_tensors()
    details = interpreter.get_tensor_details()

    weights = []
    biases = []
    for output_size, input_size in LAYER_SHAPES:
        weight_detail = next(d for d in details if tuple(d["shape"]) == (output_size, input_size))
        bias_detail = next(
            d for d in details
            if tuple(d["shape"]) == (output_size,) and d["dtype"] == np.int32
        )
        weights.append(dequantize(weight_detail, interpreter.get_tensor(weight_detail["index"])))
        biases.append(dequantize(bias_detail, interpreter.get_tensor(bias_detail["index"])))

    args.header.parent.mkdir(parents=True, exist_ok=True)
    args.source.parent.mkdir(parents=True, exist_ok=True)
    args.header.write_text(
        """#ifndef PETAPP_KWS_MODEL_WEIGHTS_H
#define PETAPP_KWS_MODEL_WEIGHTS_H

extern const float g_kws_dense1_weights[24][200];
extern const float g_kws_dense1_bias[24];
extern const float g_kws_dense2_weights[12][24];
extern const float g_kws_dense2_bias[12];
extern const float g_kws_scores_weights[3][12];
extern const float g_kws_scores_bias[3];

#endif
""",
        encoding="utf-8",
    )

    names = ("dense1", "dense2", "scores")
    declarations = ['#include "kws_model_weights.h"', ""]
    for name, weight, bias in zip(names, weights, biases):
        declarations.extend(
            [
                f"const float g_kws_{name}_weights[{weight.shape[0]}][{weight.shape[1]}] = {{",
                format_matrix(weight),
                "};",
                f"const float g_kws_{name}_bias[{bias.shape[0]}] = {{",
                format_floats(bias),
                "};",
                "",
            ]
        )
    args.source.write_text("\n".join(declarations), encoding="utf-8")
    print(f"Exported {args.model} to {args.source} and {args.header}")


if __name__ == "__main__":
    main()
