#!/usr/bin/env python3
"""Train a small Keras keyword-spotting model from local WAV samples."""

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
CLIP_SECONDS = 5
SAMPLE_COUNT = SAMPLE_RATE * CLIP_SECONDS


class LogMelSpectrogram(tf.keras.layers.Layer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mel_matrix = tf.signal.linear_to_mel_weight_matrix(
            num_mel_bins=40,
            num_spectrogram_bins=513,
            sample_rate=SAMPLE_RATE,
            lower_edge_hertz=80.0,
            upper_edge_hertz=7600.0,
        )

    def call(self, inputs):
        stft = tf.signal.stft(inputs, frame_length=640, frame_step=320, fft_length=1024)
        spectrogram = tf.abs(stft)
        mel = tf.matmul(tf.square(spectrogram), self.mel_matrix)
        log_mel = tf.math.log(mel + 1e-6)
        return tf.expand_dims(log_mel, axis=-1)

    def get_config(self):
        return super().get_config()


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
        audio = audio[:SAMPLE_COUNT]
    return audio


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
    x = np.stack([load_wav(sample.path) for sample in samples])
    y = np.array([sample.label_index for sample in samples], dtype=np.int64)
    return x, y


def build_model() -> tf.keras.Model:
    inputs = tf.keras.Input(shape=(SAMPLE_COUNT,), name="audio")
    features = LogMelSpectrogram(name="log_mel")(inputs)
    x = tf.keras.layers.Rescaling(scale=1.0)(features)
    x = tf.keras.layers.Conv2D(16, 3, padding="same", activation="relu")(x)
    x = tf.keras.layers.MaxPooling2D(pool_size=(2, 2))(x)
    x = tf.keras.layers.Conv2D(32, 3, padding="same", activation="relu")(x)
    x = tf.keras.layers.MaxPooling2D(pool_size=(2, 2))(x)
    x = tf.keras.layers.Dropout(0.2)(x)
    x = tf.keras.layers.Flatten()(x)
    x = tf.keras.layers.Dense(32, activation="relu")(x)
    outputs = tf.keras.layers.Dense(len(LABELS), activation="softmax", name="scores")(x)

    model = tf.keras.Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def export_tflite(model: tf.keras.Model, output_path: Path) -> None:
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_model = converter.convert()
    output_path.write_bytes(tflite_model)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", default="samples")
    parser.add_argument("--out", default="models/kws")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    samples_dir = Path(args.samples)
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = list_samples(samples_dir)
    if not samples:
        raise RuntimeError(f"No WAV samples found under {samples_dir}")

    for label in LABELS:
        count = sum(1 for sample in samples if LABELS[sample.label_index] == label)
        print(f"{label}: {count}")
        if count < 2:
            raise RuntimeError(f"Need at least 2 samples for label {label}")

    train_samples, validation_samples = split_samples(samples, args.validation_ratio, args.seed)
    x_train, y_train = make_arrays(train_samples)
    x_validation, y_validation = make_arrays(validation_samples)

    model = build_model()
    callbacks = [
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=8, restore_best_weights=True),
    ]
    history = model.fit(
        x_train,
        y_train,
        validation_data=(x_validation, y_validation),
        epochs=args.epochs,
        batch_size=args.batch_size,
        callbacks=callbacks,
    )

    loss, accuracy = model.evaluate(x_validation, y_validation, verbose=0)
    print(f"validation_loss={loss:.4f} validation_accuracy={accuracy:.4f}")

    keras_path = output_dir / "model.keras"
    tflite_path = output_dir / "model.tflite"
    labels_path = output_dir / "labels.json"
    history_path = output_dir / "history.json"

    model.save(keras_path)
    export_tflite(model, tflite_path)
    labels_path.write_text(json.dumps({"labels": LABELS}, indent=2), encoding="utf-8")
    history_path.write_text(json.dumps(history.history, indent=2), encoding="utf-8")

    print(f"Wrote {keras_path}")
    print(f"Wrote {tflite_path}")
    print(f"Wrote {labels_path}")


if __name__ == "__main__":
    main()
