#!/usr/bin/env python3
"""Shared speech feature extraction used by training and C golden tests."""

from __future__ import annotations

import math

import numpy as np


SAMPLE_RATE = 16000
FRAME_LENGTH = 400
FRAME_STEP = 160
FFT_SIZE = 512
MEL_BINS = 20
LOWER_EDGE_HZ = 80.0
UPPER_EDGE_HZ = 7600.0
LOG_FLOOR = 1.0e-6


def hz_to_mel(hz: float) -> float:
    return 2595.0 * math.log10(1.0 + hz / 700.0)


def mel_to_hz(mel: float) -> float:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def hann_window(length: int = FRAME_LENGTH) -> np.ndarray:
    indexes = np.arange(length, dtype=np.float32)
    return 0.5 - 0.5 * np.cos((2.0 * np.pi * indexes) / (length - 1))


def mel_filter_bank(
    mel_bins: int = MEL_BINS,
    fft_size: int = FFT_SIZE,
    sample_rate: int = SAMPLE_RATE,
    lower_edge_hz: float = LOWER_EDGE_HZ,
    upper_edge_hz: float = UPPER_EDGE_HZ,
) -> np.ndarray:
    spectrogram_bins = fft_size // 2 + 1
    lower_mel = hz_to_mel(lower_edge_hz)
    upper_mel = hz_to_mel(upper_edge_hz)
    mel_points = np.linspace(lower_mel, upper_mel, mel_bins + 2)
    hz_points = np.array([mel_to_hz(point) for point in mel_points], dtype=np.float32)
    frequencies = np.arange(spectrogram_bins, dtype=np.float32) * sample_rate / fft_size

    weights = np.zeros((spectrogram_bins, mel_bins), dtype=np.float32)
    for mel_index in range(mel_bins):
        lower = hz_points[mel_index]
        center = hz_points[mel_index + 1]
        upper = hz_points[mel_index + 2]

        lower_slope = (frequencies - lower) / (center - lower)
        upper_slope = (upper - frequencies) / (upper - center)
        weights[:, mel_index] = np.maximum(0.0, np.minimum(lower_slope, upper_slope))

    return weights


def log_mel_frame(pcm_frame: np.ndarray) -> np.ndarray:
    if pcm_frame.shape[0] != FRAME_LENGTH:
        raise ValueError(f"pcm_frame must have {FRAME_LENGTH} samples")

    audio = pcm_frame.astype(np.float32) / 32768.0
    windowed = audio * hann_window()
    spectrum = np.fft.rfft(windowed, n=FFT_SIZE)
    power = np.square(np.abs(spectrum)).astype(np.float32)
    mel_energy = power @ mel_filter_bank()
    return np.log(mel_energy + LOG_FLOOR).astype(np.float32)


def log_mel_spectrogram(pcm: np.ndarray) -> np.ndarray:
    if pcm.ndim != 1:
        raise ValueError("pcm must be a 1-D array")
    if pcm.shape[0] < FRAME_LENGTH:
        pcm = np.pad(pcm, (0, FRAME_LENGTH - pcm.shape[0]))

    frames: list[np.ndarray] = []
    for start in range(0, pcm.shape[0] - FRAME_LENGTH + 1, FRAME_STEP):
        frames.append(log_mel_frame(pcm[start:start + FRAME_LENGTH]))
    return np.stack(frames).astype(np.float32)
