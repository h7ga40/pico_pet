#!/usr/bin/env python3
"""Train a tiny KWS model using device-friendly audio features."""

import argparse
import json
import math
import random
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tensorflow as tf


LABELS = ("negative", "near_miss", "positive")
SAMPLE_RATE = 16000
CLIP_SECONDS = 2
SAMPLE_COUNT = SAMPLE_RATE * CLIP_SECONDS
WINDOW_SIZE = 320
WINDOW_STEP = 320
FEATURES_PER_WINDOW = 2


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

    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.shape[0] < SAMPLE_COUNT:
        audio = np.pad(audio, (0, SAMPLE_COUNT - audio.shape[0]))
    elif audio.shape[0] > SAMPLE_COUNT:
        energy_window = SAMPLE_RATE // 10
        squared = audio * audio
        cumulative = np.concatenate(([0.0], np.cumsum(squared, dtype=np.float64)))
        energies = cumulative[energy_window:] - cumulative[:-energy_window]
        peak_center = int(np.argmax(energies)) + energy_window // 2
        start = max(0, min(peak_center - SAMPLE_COUNT // 2, audio.shape[0] - SAMPLE_COUNT))
        audio = audio[start:start + SAMPLE_COUNT]
    return audio


def extract_features(audio: np.ndarray) -> np.ndarray:
    features: list[float] = []
    for start in range(0, SAMPLE_COUNT - WINDOW_SIZE + 1, WINDOW_STEP):
        window = audio[start:start + WINDOW_SIZE]
        rms = math.sqrt(float(np.mean(window * window)))
        peak = float(np.max(np.abs(window)))
        features.extend((rms, peak))
    return np.array(features, dtype=np.float32)


def list_samples(samples_dir: Path) -> list[Sample]:
    samples: list[Sample] = []
    for label_index, label in enumerate(LABELS):
        label_dir = samples_dir / label
        for wav_path in sorted(label_dir.glob("*.wav")):
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
    x = np.stack([extract_features(load_wav(sample.path)) for sample in samples])
    y = np.array([sample.label_index for sample in samples], dtype=np.int64)
    return x, y


def build_model(input_size: int) -> tf.keras.Model:
    inputs = tf.keras.Input(shape=(input_size,), name="features")
    x = tf.keras.layers.Dense(24, activation="relu")(inputs)
    x = tf.keras.layers.Dense(12, activation="relu")(x)
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
        for row in x_train[: min(len(x_train), 64)]:
            yield [row[np.newaxis, :].astype(np.float32)]
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
    parser.add_argument("--out", default="models/kws_tiny")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    samples = list_samples(Path(args.samples))
    if not samples:
        raise RuntimeError("No WAV samples found")

    train_samples, validation_samples = split_samples(samples, args.validation_ratio, args.seed)
    x_train, y_train = make_arrays(train_samples)
    x_validation, y_validation = make_arrays(validation_samples)

    print(f"feature_size={x_train.shape[1]}")
    for label in LABELS:
        count = sum(1 for sample in samples if LABELS[sample.label_index] == label)
        print(f"{label}: {count}")

    model = build_model(x_train.shape[1])
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
                "window_size": WINDOW_SIZE,
                "window_step": WINDOW_STEP,
                "features_per_window": FEATURES_PER_WINDOW,
                "feature_size": int(x_train.shape[1]),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "history.json").write_text(json.dumps(history.history, indent=2), encoding="utf-8")
    print(f"Wrote {output_dir / 'model_int8.tflite'}")


if __name__ == "__main__":
    main()
