#!/usr/bin/env python3
"""Record raw PCM from PicoWakeup over USB serial and save it as a WAV file."""

import argparse
import sys
import time
import wave
from pathlib import Path

import serial


def read_until_pcm_header(port: serial.Serial) -> tuple[int, int]:
    while True:
        line = port.readline().decode("ascii", errors="replace").strip()
        if line:
            print(line)
        if line.startswith("PCM16 "):
            _, sample_count, sample_rate = line.split()
            return int(sample_count), int(sample_rate)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", help="Serial port, for example COM5")
    parser.add_argument("output", help="Output WAV path")
    parser.add_argument("--seconds", type=int, default=5)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout-padding", type=float, default=10.0)
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with serial.Serial(args.port, args.baud, timeout=1) as port:
        port.reset_input_buffer()
        port.write(f"record {args.seconds}\n".encode("ascii"))
        port.flush()

        sample_count, sample_rate = read_until_pcm_header(port)
        byte_count = sample_count * 2
        print(f"Reading {sample_count} samples at {sample_rate} Hz")

        deadline = time.monotonic() + args.seconds + args.timeout_padding
        chunks: list[bytes] = []
        received = 0

        while received < byte_count and time.monotonic() < deadline:
            chunk = port.read(min(4096, byte_count - received))
            if not chunk:
                continue
            chunks.append(chunk)
            received += len(chunk)
            print(f"\rReceived {received}/{byte_count} bytes", end="", file=sys.stderr)

        print(file=sys.stderr)

        if received != byte_count:
            raise RuntimeError(f"Expected {byte_count} bytes, got {received} bytes")

        pcm = b"".join(chunks)

    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)

    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
