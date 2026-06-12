#!/usr/bin/env python3
"""Convert a .tflite file into C source/header files for Pico firmware."""

import argparse
from pathlib import Path


def format_bytes(data: bytes, columns: int) -> str:
    lines: list[str] = []
    for offset in range(0, len(data), columns):
        chunk = data[offset:offset + columns]
        values = ", ".join(f"0x{byte:02x}" for byte in chunk)
        lines.append(f"    {values},")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Input .tflite file")
    parser.add_argument("--source", default="src/kws_model_data.c")
    parser.add_argument("--header", default="include/kws_model_data.h")
    parser.add_argument("--array-name", default="g_kws_model_data")
    parser.add_argument("--length-name", default="g_kws_model_data_len")
    parser.add_argument("--columns", type=int, default=12)
    args = parser.parse_args()

    input_path = Path(args.input)
    source_path = Path(args.source)
    header_path = Path(args.header)
    data = input_path.read_bytes()

    source_path.parent.mkdir(parents=True, exist_ok=True)
    header_path.parent.mkdir(parents=True, exist_ok=True)

    guard = header_path.name.upper().replace(".", "_").replace("-", "_")

    header_path.write_text(
        "\n".join(
            [
                f"#ifndef {guard}",
                f"#define {guard}",
                "",
                "#include <stddef.h>",
                "#include <stdint.h>",
                "",
                f"extern const uint8_t {args.array_name}[];",
                f"extern const size_t {args.length_name};",
                "",
                f"#endif  // {guard}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    source_path.write_text(
        "\n".join(
            [
                f'#include "{header_path.name}"',
                "",
                f"const uint8_t {args.array_name}[] __attribute__((aligned(16))) = {{",
                format_bytes(data, args.columns),
                "};",
                "",
                f"const size_t {args.length_name} = sizeof({args.array_name});",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Read {input_path} ({len(data)} bytes)")
    print(f"Wrote {header_path}")
    print(f"Wrote {source_path}")


if __name__ == "__main__":
    main()
