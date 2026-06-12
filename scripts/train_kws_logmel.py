#!/usr/bin/env python3
"""Train a KWS model from shared Log-Mel features."""

from __future__ import annotations

import argparse
import json
import math
import random
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tensorflow as tf

from speech_features import (
    FRAME_LENGTH,
    FRAME_STEP,
    LOG_FLOOR,
    MEL_BINS,
    SAMPLE_RATE,
    log_mel_spectrogram,
)


LABELS = ("negative", "near_miss", "positive")
CLIP_SECONDS = 2
SAMPLE_COUNT = SAMPLE_RATE * CLIP_SECONDS


@dataclass(frozen=True)
class Sample:
    path: Path
    label_index: int


def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()
        pcm = wav.readframes(frames)

    if channels != 1 or sample_width != 2 or sample_rate != SAMPLE_RATE:
        raise ValueError(f"{path} must be 16 kHz, 16-bit, mono WAV")

    audio = np.frombuffer(pcm, dtype=np.int16)
    if audio.shape[0] < SAMPLE_COUNT:
        audio = np.pad(audio, (0, SAMPLE_COUNT - audio.shape[0]))
    elif audio.shape[0] > SAMPLE_COUNT:
        audio = audio[:SAMPLE_COUNT]
    return audio


def extract_features(path: Path) -> np.ndarray:
    features = log_mel_spectrogram(load_wav(path))
    return features[..., np.newaxis].astype(np.float32)


def list_samples(samples_dir: Path) -> list[Sample]:
    samples: list[Sample] = []
    for label_index, label in enumerate(LABELS):
        for wav_path in sorted((samples_dir / label).glob("*.wav")):
            samples.append(Sample(wav_path, label_index))
    return samples


def split_samples(samples: list[Sample], validation_ratio: float, seed: int) -> tuple[list[Sample], list[Sample]]:
    rng = random.Random(seed)
    train: list[Sample] = []
    validation: list[Sample] = []
    for label_index in range(len(LABELS)):
        label_samples = [sample for sample in samples if sample.label_index == label_index]
        rng.shuffle(label_samples)
        validation_count = max(1, math.ceil(len(label_samples) * validation_ratio))
        validation.extend(label_samples[:validation_count])
        train.extend(label_samples[validation_count:])
    rng.shuffle(train)
    rng.shuffle(validation)
    return train, validation


def make_arrays(samples: list[Sample]) -> tuple[np.ndarray, np.ndarray]:
    x = np.stack([extract_features(sample.path) for sample in samples])
    y = np.array([sample.label_index for sample in samples], dtype=np.int64)
    return x, y


def build_model(input_shape: tuple[int, int, int]) -> tf.keras.Model:
    inputs = tf.keras.Input(shape=input_shape, name="log_mel")
    x = tf.keras.layers.Conv2D(12, 3, padding="same", activation="relu")(inputs)
    x = tf.keras.layers.MaxPooling2D(pool_size=(2, 2))(x)
    x = tf.keras.layers.Conv2D(24, 3, padding="same", activation="relu")(x)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dense(16, activation="relu")(x)
    outputs = tf.keras.layers.Dense(len(LABELS), activation="softmax", name="scores")(x)
    model = tf.keras.Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def representative_dataset(x_train: np.ndarray):
    def generate():
        for sample in x_train[: min(len(x_train), 64)]:
            yield [sample[np.newaxis, ...].astype(np.float32)]
    return generate


def export_tflite(model: tf.keras.Model, output_path: Path, x_train: np.ndarray) -> None:
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative_dataset(x_train)
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    output_path.write_bytes(converter.convert())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", default="samples")
    parser.add_argument("--out", default="models/kws_logmel")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    samples = list_samples(Path(args.samples))
    if not samples:
        raise RuntimeError("No WAV samples found")
    for label in LABELS:
        print(f"{label}: {sum(1 for sample in samples if LABELS[sample.label_index] == label)}")

    train_samples, validation_samples = split_samples(samples, args.validation_ratio, args.seed)
    x_train, y_train = make_arrays(train_samples)
    x_validation, y_validation = make_arrays(validation_samples)
    print(f"feature_shape={x_train.shape[1:]}")

    model = build_model(tuple(x_train.shape[1:]))
    history = model.fit(
        x_train,
        y_train,
        validation_data=(x_validation, y_validation),
        epochs=args.epochs,
        batch_size=args.batch_size,
        callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=10, restore_best_weights=True)],
    )
    loss, accuracy = model.evaluate(x_validation, y_validation, verbose=0)
    print(f"validation_loss={loss:.4f} validation_accuracy={accuracy:.4f}")

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save(output_dir / "model.keras")
    export_tflite(model, output_dir / "model_int8.tflite", x_train)
    (output_dir / "labels.json").write_text(json.dumps({"labels": LABELS}, indent=2), encoding="utf-8")
    (output_dir / "feature_config.json").write_text(
        json.dumps(
            {
                "sample_rate": SAMPLE_RATE,
                "clip_seconds": CLIP_SECONDS,
                "sample_count": SAMPLE_COUNT,
                "frame_length": FRAME_LENGTH,
                "frame_step": FRAME_STEP,
                "mel_bins": MEL_BINS,
                "log_floor": LOG_FLOOR,
                "feature_shape": list(x_train.shape[1:]),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "history.json").write_text(json.dumps(history.history, indent=2), encoding="utf-8")
    print(f"Wrote {output_dir / 'model_int8.tflite'}")


if __name__ == "__main__":
    main()
