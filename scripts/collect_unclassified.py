#!/usr/bin/env python3
"""Continuously record Pico audio and save loud regions as 2-second WAV clips."""

import argparse
import queue
import threading
from pathlib import Path

import numpy as np
import serial

from collect_sample import next_sample_path
from record_wav import capture_pcm, write_wav


SAMPLE_RATE = 16000
CLIP_SECONDS = 2
CLIP_SAMPLES = SAMPLE_RATE * CLIP_SECONDS
FRAME_SAMPLES = SAMPLE_RATE // 50


def loud_clip_centers(
    audio: np.ndarray,
    absolute_threshold: float,
    noise_multiplier: float,
    merge_gap_ms: int,
    minimum_loud_ms: int,
) -> tuple[list[int], float]:
    frame_count = audio.size // FRAME_SAMPLES
    if frame_count == 0:
        return [], absolute_threshold

    frames = audio[:frame_count * FRAME_SAMPLES].reshape(frame_count, FRAME_SAMPLES)
    normalized = frames.astype(np.float32) / 32768.0
    rms = np.sqrt(np.mean(normalized * normalized, axis=1))
    noise_floor = float(np.percentile(rms, 20))
    threshold = max(absolute_threshold, noise_floor * noise_multiplier)
    loud = rms >= threshold

    merge_frames = max(1, merge_gap_ms // 20)
    loud_indices = np.flatnonzero(loud)
    if loud_indices.size == 0:
        return [], threshold

    regions: list[tuple[int, int]] = []
    start = previous = int(loud_indices[0])
    for index_value in loud_indices[1:]:
        index = int(index_value)
        if index - previous > merge_frames:
            regions.append((start, previous + 1))
            start = index
        previous = index
    regions.append((start, previous + 1))

    minimum_frames = max(1, minimum_loud_ms // 20)
    centers = []
    previous_center = -CLIP_SAMPLES
    for start, end in regions:
        if int(np.count_nonzero(loud[start:end])) < minimum_frames:
            continue
        peak_frame = start + int(np.argmax(rms[start:end]))
        center = peak_frame * FRAME_SAMPLES + FRAME_SAMPLES // 2
        if center - previous_center < CLIP_SAMPLES:
            continue
        centers.append(center)
        previous_center = center
    return centers, threshold


def extract_clip(audio: np.ndarray, center: int) -> np.ndarray:
    start = max(0, min(center - CLIP_SAMPLES // 2, max(0, audio.size - CLIP_SAMPLES)))
    clip = audio[start:start + CLIP_SAMPLES]
    if clip.size < CLIP_SAMPLES:
        clip = np.pad(clip, (0, CLIP_SAMPLES - clip.size))
    return clip.astype("<i2", copy=False)


def record_chunks(
    port: serial.Serial,
    seconds: int,
    baud: int,
    output: queue.Queue,
    stop_event: threading.Event,
) -> None:
    try:
        while not stop_event.is_set():
            output.put(capture_pcm(port, seconds, baud=baud))
    except Exception as error:
        output.put(error)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", help="Serial port, for example COM5")
    parser.add_argument("--root", type=Path, default=Path("samples"))
    parser.add_argument("--chunk-seconds", type=int, default=10, choices=range(2, 11))
    parser.add_argument("--threshold", type=float, default=0.01, help="Minimum normalized RMS")
    parser.add_argument("--noise-multiplier", type=float, default=3.0)
    parser.add_argument("--merge-gap-ms", type=int, default=300)
    parser.add_argument("--minimum-loud-ms", type=int, default=100)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--max-clips", type=int, default=0, help="Stop after this many clips; 0 runs until Ctrl+C")
    args = parser.parse_args()

    saved = 0
    print("Loud-region collection started. Press Ctrl+C to stop.")
    with serial.Serial(args.port, args.baud, timeout=1) as port:
        chunks: queue.Queue = queue.Queue(maxsize=3)
        stop_event = threading.Event()
        recorder = threading.Thread(
            target=record_chunks,
            args=(port, args.chunk_seconds, args.baud, chunks, stop_event),
            daemon=True,
        )
        recorder.start()
        try:
            while args.max_clips == 0 or saved < args.max_clips:
                captured = chunks.get()
                if isinstance(captured, Exception):
                    raise captured
                pcm, sample_rate = captured
                if sample_rate != SAMPLE_RATE:
                    raise RuntimeError(f"Expected {SAMPLE_RATE} Hz, got {sample_rate} Hz")
                audio = np.frombuffer(pcm, dtype="<i2")
                centers, threshold = loud_clip_centers(
                    audio,
                    args.threshold,
                    args.noise_multiplier,
                    args.merge_gap_ms,
                    args.minimum_loud_ms,
                )
                if not centers:
                    print(f"No loud region found (RMS threshold={threshold:.4f})")
                    continue
                for center in centers:
                    path = next_sample_path(args.root, "unclassified", "unclassified")
                    write_wav(path, extract_clip(audio, center).tobytes(), SAMPLE_RATE)
                    saved += 1
                    print(f"{path}: center={center / SAMPLE_RATE:.2f}s threshold={threshold:.4f}")
                    if args.max_clips and saved >= args.max_clips:
                        break
        except KeyboardInterrupt:
            print("\nCollection stopped")
        finally:
            stop_event.set()


if __name__ == "__main__":
    main()
