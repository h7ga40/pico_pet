#!/usr/bin/env python3
"""Split a Codex pet spritesheet into RGB565 frame binaries and a C header."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_STATE_SPECS = (
    ("idle", 6),
    ("running-right", 8),
    ("running-left", 8),
    ("waving", 4),
    ("jumping", 5),
    ("failed", 8),
    ("waiting", 6),
    ("running", 6),
    ("review", 6),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Split a 9-state x 8-frame Codex pet spritesheet into RGB565 "
            "big-endian frame .bin files."
        )
    )
    parser.add_argument(
        "-i",
        "--input",
        default=Path("pets/zundamon/spritesheet.webp"),
        type=Path,
        help="Input spritesheet image (default: pets/zundamon/spritesheet.webp)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=Path("build/generated/pet"),
        type=Path,
        help="Directory for generated frame .bin files",
    )
    parser.add_argument(
        "--header",
        default=None,
        type=Path,
        help="Output pet_images.h path (default: <output-dir>/pet_images.h)",
    )
    parser.add_argument(
        "--source",
        default=None,
        type=Path,
        help="Output pet_images.c path (default: <output-dir>/pet_images.c)",
    )
    parser.add_argument(
        "--states",
        default=",".join(state for state, _ in DEFAULT_STATE_SPECS),
        help="Comma-separated state names, one per spritesheet row",
    )
    parser.add_argument(
        "--frame-counts",
        default=",".join(str(count) for _, count in DEFAULT_STATE_SPECS),
        help=(
            "Comma-separated expected frame counts, one per state. "
            "Use an empty string to disable count validation."
        ),
    )
    parser.add_argument("--columns", type=int, default=8, help="Frame columns")
    parser.add_argument("--rows", type=int, default=9, help="State rows")
    parser.add_argument("--frame-width", type=int, default=None)
    parser.add_argument("--frame-height", type=int, default=None)
    parser.add_argument(
        "--transparent-color",
        default="0x0000",
        help="RGB565 color used for transparent pixels (default: 0x0000)",
    )
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=0,
        help="Alpha value at or below this is treated as transparent",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove old generated .bin/.obj/.a files first",
    )
    parser.add_argument(
        "--objcopy",
        default=None,
        help="objcopy command. If omitted, object files are not generated.",
    )
    parser.add_argument(
        "--object-dir",
        default=None,
        type=Path,
        help="Directory for generated object files (default: <output-dir>)",
    )
    parser.add_argument(
        "--objcopy-input-format",
        default="binary",
        help="objcopy input format (default: binary)",
    )
    parser.add_argument(
        "--objcopy-output-format",
        default=None,
        help="objcopy output format, for example elf32-littlearm",
    )
    parser.add_argument(
        "--objcopy-architecture",
        default=None,
        help="objcopy binary architecture, for example armv8-m.main",
    )
    parser.add_argument(
        "--objcopy-extra-arg",
        action="append",
        default=[],
        help="Extra argument passed to objcopy. May be repeated.",
    )
    parser.add_argument(
        "--objcopy-section",
        default=None,
        help=(
            "Rename objcopy's default .data section to this section, "
            "for example .rodata or .rodata.pet_images."
        ),
    )
    parser.add_argument(
        "--objcopy-section-flags",
        default="alloc,load,readonly,data,contents",
        help=(
            "Flags used with --objcopy-section "
            "(default: alloc,load,readonly,data,contents)."
        ),
    )
    parser.add_argument(
        "--ar",
        default=None,
        help="ar command. Required when --archive is used.",
    )
    parser.add_argument(
        "--ar-flags",
        default="rcs",
        help="Flags passed to ar before the archive path (default: rcs)",
    )
    parser.add_argument(
        "--archive",
        default=None,
        type=Path,
        help="Output static archive containing generated image object files.",
    )
    return parser.parse_args()


def require_pillow():
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            "error: Pillow is required to read WebP files. "
            "Install it in the Python used by CMake: python -m pip install Pillow"
        ) from exc
    return Image


def c_identifier(value: str) -> str:
    value = value.replace("-", "_")
    value = re.sub(r"[^0-9A-Za-z_]", "_", value.strip().lower())
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        raise ValueError("empty state name is not allowed")
    if value[0].isdigit():
        value = f"state_{value}"
    return value


def rgb888_to_rgb565(r: int, g: int, b: int) -> int:
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def parse_rgb565(value: str) -> int:
    color = int(value, 0)
    if not 0 <= color <= 0xFFFF:
        raise ValueError(f"transparent color out of RGB565 range: {value}")
    return color


def is_empty_frame(frame, alpha_threshold: int) -> bool:
    if "A" in frame.getbands():
        alpha = frame.getchannel("A")
        return alpha.getextrema()[1] <= alpha_threshold

    # Fallback for spritesheets without alpha: a fully uniform cell is considered empty.
    extrema = frame.convert("RGB").getextrema()
    return all(lo == hi for lo, hi in extrema)


def frame_to_rgb565_bytes(frame, transparent_color: int, alpha_threshold: int) -> bytes:
    rgba = frame.convert("RGBA")
    output = bytearray()
    for r, g, b, a in rgba.getdata():
        if a <= alpha_threshold:
            rgb565 = transparent_color
        else:
            rgb565 = rgb888_to_rgb565(r, g, b)
        output.append((rgb565 >> 8) & 0xFF)
        output.append(rgb565 & 0xFF)
    return bytes(output)


def write_if_changed(path: Path, data: bytes | str) -> None:
    old = None
    if path.exists():
        old = path.read_bytes() if isinstance(data, bytes) else path.read_text()
    if old == data:
        return
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8", newline="\n")


def objcopy_binary_symbol_prefix(filename: str) -> str:
    return "_binary_" + re.sub(r"[^0-9A-Za-z_]", "_", filename)


def run_command(command: list[str], cwd: Path) -> None:
    printable = " ".join(command)
    print(printable)
    subprocess.run(command, cwd=cwd, check=True)


def objcopy_frame(
    objcopy: str,
    input_format: str,
    output_format: str | None,
    architecture: str | None,
    extra_args: list[str],
    section: str | None,
    section_flags: str,
    bin_path: Path,
    object_path: Path,
    symbol_base: str,
) -> None:
    object_path.parent.mkdir(parents=True, exist_ok=True)
    default_prefix = objcopy_binary_symbol_prefix(bin_path.name)
    command = [
        objcopy,
        "-I",
        input_format,
    ]
    if output_format is not None:
        command.extend(["-O", output_format])
    if architecture is not None:
        command.append(f"--binary-architecture={architecture}")
    command.extend(extra_args)
    if section is not None:
        section_name = section if section.startswith(".") else f".{section}"
        command.append(f"--rename-section=.data={section_name},{section_flags}")
    command.extend(
        [
            f"--redefine-sym={default_prefix}_start={symbol_base}_start",
            f"--redefine-sym={default_prefix}_end={symbol_base}_end",
            f"--redefine-sym={default_prefix}_size={symbol_base}_size",
            bin_path.name,
            str(object_path),
        ]
    )
    run_command(command, cwd=bin_path.parent)


def archive_objects(ar: str, ar_flags: str, archive: Path, objects: list[Path]) -> None:
    if not objects:
        raise ValueError("no object files were generated for archive")
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        archive.unlink()
    command = [ar, ar_flags, str(archive), *(str(path) for path in objects)]
    run_command(command, cwd=Path.cwd())


def build_header(
    states: list[str],
    counts: dict[str, int],
    expected_counts: dict[str, int] | None,
    frame_width: int,
    frame_height: int,
    generated_files: list[str],
) -> str:
    lines = [
        "/* Auto-generated by scripts/pet_spritesheet_to_bins.py. */",
        "#ifndef PET_IMAGES_H",
        "#define PET_IMAGES_H",
        "",
        "#include <stdint.h>",
        "#include <stddef.h>",
        "",
        f"#define PET_IMAGE_WIDTH {frame_width}",
        f"#define PET_IMAGE_HEIGHT {frame_height}",
        "#define PET_IMAGE_BYTES_PER_PIXEL 2",
        f"#define PET_IMAGE_FRAME_BYTES ({frame_width}u * {frame_height}u * PET_IMAGE_BYTES_PER_PIXEL)",
        f"#define PET_IMAGE_STATE_COUNT {len(states)}",
        "",
        "typedef struct {",
        "    const uint8_t *data;",
        "    const uint8_t *end;",
        "    uintptr_t size;",
        "} pet_image_t;",
        "",
    ]

    for state in states:
        macro = state.upper()
        lines.append(f"#define PET_{macro}_FRAME_COUNT {counts[state]}")
        if expected_counts is not None:
            lines.append(f"#define PET_{macro}_EXPECTED_FRAME_COUNT {expected_counts[state]}")

    lines.extend(
        [
            "",
            "typedef enum {",
        ]
    )
    for index, state in enumerate(states):
        comma = "," if index + 1 < len(states) else ""
        lines.append(f"    PET_STATE_{state.upper()} = {index}{comma}")
    lines.extend(
        [
            "} pet_state_t;",
            "",
        ]
    )

    for state in states:
        lines.append(f"extern const pet_image_t pet_{state}_frames[PET_{state.upper()}_FRAME_COUNT];")

    lines.extend(
        [
            "",
            "extern const pet_image_t *const pet_state_frames[PET_IMAGE_STATE_COUNT];",
            "extern const uint8_t pet_state_frame_counts[PET_IMAGE_STATE_COUNT];",
            "",
            "/* Generated frame binaries, relative to the output directory: */",
        ]
    )
    for filename in generated_files:
        lines.append(f"/* {filename} */")

    lines.extend(["", "#endif /* PET_IMAGES_H */", ""])
    return "\n".join(lines)


def build_source(states: list[str], frames_by_state: dict[str, list[str]]) -> str:
    lines = [
        "/* Auto-generated by scripts/pet_spritesheet_to_bins.py. */",
        '#include "pet_images.h"',
        "",
        "/*",
        " * The linked binary objects must provide these symbols.",
        " * For each <state>_frame_<n>.bin, redefine objcopy symbols to:",
        " *   pet_<state>_frame_<n>_start",
        " *   pet_<state>_frame_<n>_end",
        " *   pet_<state>_frame_<n>_size",
        " */",
        "",
    ]

    for state in states:
        for symbol_base in frames_by_state[state]:
            lines.extend(
                [
                    f"extern const uint8_t {symbol_base}_start[];",
                    f"extern const uint8_t {symbol_base}_end[];",
                    f"extern const uint8_t {symbol_base}_size[];",
                ]
            )

    lines.append("")

    for state in states:
        frame_symbols = frames_by_state[state]
        lines.append(f"const pet_image_t pet_{state}_frames[PET_{state.upper()}_FRAME_COUNT] = {{")
        if frame_symbols:
            for symbol_base in frame_symbols:
                lines.append(
                    f"    {{ {symbol_base}_start, {symbol_base}_end, "
                    f"(uintptr_t){symbol_base}_size }},"
                )
        lines.append("};")
        lines.append("")

    lines.append("const pet_image_t *const pet_state_frames[PET_IMAGE_STATE_COUNT] = {")
    for state in states:
        lines.append(f"    pet_{state}_frames,")
    lines.append("};")
    lines.append("")

    lines.append("const uint8_t pet_state_frame_counts[PET_IMAGE_STATE_COUNT] = {")
    for state in states:
        lines.append(f"    PET_{state.upper()}_FRAME_COUNT,")
    lines.append("};")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    Image = require_pillow()

    states = [c_identifier(item) for item in args.states.split(",") if item.strip()]
    if len(states) != args.rows:
        raise ValueError(f"--states has {len(states)} names, but --rows is {args.rows}")
    if len(set(states)) != len(states):
        raise ValueError("--states contains duplicate names after sanitizing")

    expected_counts = None
    if args.frame_counts.strip():
        expected_values = [int(item, 0) for item in args.frame_counts.split(",")]
        if len(expected_values) != len(states):
            raise ValueError(
                f"--frame-counts has {len(expected_values)} values, "
                f"but --states has {len(states)} names"
            )
        expected_counts = dict(zip(states, expected_values))

    image = Image.open(args.input).convert("RGBA")
    sheet_width, sheet_height = image.size
    frame_width = args.frame_width or sheet_width // args.columns
    frame_height = args.frame_height or sheet_height // args.rows

    if frame_width * args.columns != sheet_width:
        raise ValueError(f"sheet width {sheet_width} is not divisible by {args.columns}")
    if frame_height * args.rows != sheet_height:
        raise ValueError(f"sheet height {sheet_height} is not divisible by {args.rows}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    object_dir = args.object_dir or args.output_dir
    object_dir.mkdir(parents=True, exist_ok=True)
    header = args.header or (args.output_dir / "pet_images.h")
    source = args.source or (args.output_dir / "pet_images.c")
    header.parent.mkdir(parents=True, exist_ok=True)
    source.parent.mkdir(parents=True, exist_ok=True)

    if args.clean:
        for old_file in args.output_dir.glob("*_frame_*.bin"):
            old_file.unlink()
        for old_file in object_dir.glob("*_frame_*.obj"):
            old_file.unlink()
        if args.archive is not None and args.archive.exists():
            args.archive.unlink()

    if args.archive is not None and args.ar is None:
        raise ValueError("--ar is required when --archive is used")
    if args.archive is not None and args.objcopy is None:
        raise ValueError("--objcopy is required when --archive is used")

    transparent_color = parse_rgb565(args.transparent_color)
    counts = {state: 0 for state in states}
    generated_files: list[str] = []
    frames_by_state = {state: [] for state in states}
    object_files: list[Path] = []

    for row, state in enumerate(states):
        for column in range(args.columns):
            left = column * frame_width
            upper = row * frame_height
            frame = image.crop((left, upper, left + frame_width, upper + frame_height))
            if is_empty_frame(frame, args.alpha_threshold):
                continue

            counts[state] += 1
            filename = f"{state}_frame_{counts[state]}.bin"
            symbol_base = f"pet_{state}_frame_{counts[state]}"
            bin_path = args.output_dir / filename
            write_if_changed(
                bin_path,
                frame_to_rgb565_bytes(frame, transparent_color, args.alpha_threshold),
            )
            generated_files.append(filename)
            frames_by_state[state].append(symbol_base)

            if args.objcopy is not None:
                object_path = object_dir / f"{state}_frame_{counts[state]}.obj"
                objcopy_frame(
                    args.objcopy,
                    args.objcopy_input_format,
                    args.objcopy_output_format,
                    args.objcopy_architecture,
                    args.objcopy_extra_arg,
                    args.objcopy_section,
                    args.objcopy_section_flags,
                    bin_path,
                    object_path,
                    symbol_base,
                )
                object_files.append(object_path)

    write_if_changed(
        header,
        build_header(states, counts, expected_counts, frame_width, frame_height, generated_files),
    )
    write_if_changed(source, build_source(states, frames_by_state))

    if expected_counts is not None:
        mismatches = [
            f"{state}: generated {counts[state]}, expected {expected_counts[state]}"
            for state in states
            if counts[state] != expected_counts[state]
        ]
        if mismatches:
            raise ValueError("frame count mismatch: " + "; ".join(mismatches))

    if args.archive is not None:
        archive_objects(args.ar, args.ar_flags, args.archive, object_files)

    total = sum(counts.values())
    print(
        f"generated {total} frame binaries in {args.output_dir} "
        f"({frame_width}x{frame_height}, RGB565 big-endian)"
    )
    print(f"generated header: {header}")
    print(f"generated source: {source}")
    if args.archive is not None:
        print(f"generated archive: {args.archive}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
