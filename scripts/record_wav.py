#!/usr/bin/env python3
"""Record raw PCM from PicoWakeup over USB serial and save it as a WAV file."""

import argparse
import sys
import time
import wave
from pathlib import Path

import serial


class RecordCommandError(RuntimeError):
    pass


def read_until_pcm_header(port: serial.Serial, timeout_seconds: float) -> tuple[int, int]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        line = port.readline().decode("ascii", errors="replace").strip()
        if line:
            print(line)
        if line.startswith("Unknown command:"):
            raise RecordCommandError(line)
        if line.startswith("PCM16 "):
            _, sample_count, sample_rate = line.split()
            return int(sample_count), int(sample_rate)
    raise RecordCommandError("Timed out waiting for PCM16 header")


def capture_pcm(
    port: serial.Serial,
    seconds: int,
    timeout_padding: float = 10.0,
    retries: int = 3,
    header_timeout: float = 5.0,
    baud: int = 115200,
) -> tuple[bytes, int]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        port.reset_input_buffer()
        if attempt > 1:
            print(f"Retrying record command ({attempt}/{retries})")
        time.sleep(0.25)
        port.write(f"record {seconds}\n".encode("ascii"))
        port.flush()
        try:
            sample_count, sample_rate = read_until_pcm_header(port, header_timeout)
            break
        except RecordCommandError as error:
            last_error = error
    else:
        raise RecordCommandError(
            f"record command failed after {retries} attempts: {last_error}"
        ) from last_error

    byte_count = sample_count * 2
    print(f"Reading {sample_count} samples at {sample_rate} Hz")

    # Pico stdio may mirror output to a 115200 bps UART even when the PC reads USB CDC.
    # Allow for 10 serial bits per byte and keep extending the deadline on progress.
    transfer_seconds = byte_count * 10.0 / max(baud, 1)
    progress_timeout = max(timeout_padding, transfer_seconds * 0.25)
    deadline = time.monotonic() + max(seconds, transfer_seconds) + timeout_padding
    chunks: list[bytes] = []
    received = 0
    while received < byte_count and time.monotonic() < deadline:
        chunk = port.read(min(4096, byte_count - received))
        if not chunk:
            continue
        chunks.append(chunk)
        received += len(chunk)
        deadline = max(deadline, time.monotonic() + progress_timeout)
        print(f"\rReceived {received}/{byte_count} bytes", end="", file=sys.stderr)
    print(file=sys.stderr)

    if received != byte_count:
        raise RuntimeError(f"Expected {byte_count} bytes, got {received} bytes")
    return b"".join(chunks), sample_rate


def write_wav(path: Path, pcm: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", help="Serial port, for example COM5")
    parser.add_argument("output", help="Output WAV path")
    parser.add_argument("--seconds", type=int, default=2)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout-padding", type=float, default=10.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--header-timeout", type=float, default=5.0)
    args = parser.parse_args()

    output_path = Path(args.output)
    with serial.Serial(args.port, args.baud, timeout=1) as port:
        pcm, sample_rate = capture_pcm(
            port,
            args.seconds,
            args.timeout_padding,
            args.retries,
            args.header_timeout,
            args.baud,
        )

    write_wav(output_path, pcm, sample_rate)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
