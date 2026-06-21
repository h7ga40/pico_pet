"""Stream a 16 kHz mono PCM16 WAV file to PetApp over USB CDC."""

from __future__ import annotations

import argparse
import time
import wave
from pathlib import Path

import serial


SAMPLE_RATE = 16_000


def read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1:
            raise ValueError("WAV must be mono")
        if wav.getsampwidth() != 2:
            raise ValueError("WAV must be 16-bit PCM")
        if wav.getframerate() != SAMPLE_RATE:
            raise ValueError(f"WAV must use {SAMPLE_RATE} Hz")
        if wav.getcomptype() != "NONE":
            raise ValueError("WAV must be uncompressed PCM")
        return wav.readframes(wav.getnframes())


def read_line(port: serial.Serial, deadline: float) -> str:
    while time.monotonic() < deadline:
        line = port.readline()
        if line:
            return line.decode("utf-8", errors="replace").strip()
    raise TimeoutError("timed out waiting for Pico response")


def stream_wav(port: serial.Serial, pcm: bytes, timeout_seconds: float) -> None:
    sample_count = len(pcm) // 2
    port.write(f"play {sample_count} {SAMPLE_RATE}\n".encode("ascii"))
    port.flush()

    offset = 0
    received_complete = False
    deadline = time.monotonic() + timeout_seconds
    while not received_complete:
        line = read_line(port, deadline)
        print(line)
        if line.startswith("ERROR"):
            raise RuntimeError(line)
        if line.startswith("READY PLAY "):
            block_samples = int(line.removeprefix("READY PLAY "))
            block_bytes = block_samples * 2
            if block_samples <= 0 or offset + block_bytes > len(pcm):
                raise RuntimeError(f"invalid device block request: {line}")
            port.write(pcm[offset : offset + block_bytes])
            port.flush()
            offset += block_bytes
        elif line == "PLAY RECEIVED":
            if offset != len(pcm):
                raise RuntimeError("device finished receiving before all PCM was sent")
            received_complete = True

    while True:
        line = read_line(port, deadline)
        print(line)
        if line.startswith("ERROR"):
            raise RuntimeError(line)
        if line == "PLAY DONE":
            return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="USB CDC port, for example COM5")
    parser.add_argument("wav", type=Path, help="16 kHz, mono, PCM16 WAV file")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    pcm = read_wav(args.wav)
    with serial.Serial(args.port, args.baud, timeout=0.2) as port:
        stream_wav(port, pcm, args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
