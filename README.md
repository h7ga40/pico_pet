# Pico Pet

Waveshare RP2350 Touch AMOLED 1.8でCodex Petを表示し、タッチ、加速度、
16 kHz音声入力、ウェイクワード検出、音声再生を行うアプリです。

## ペット画像

`pets/zundamon`へ`spritesheet.webp`を配置します。別のペットを使う場合は
`CMakeLists.txt`の`PET_NAME`を変更してください。

```cmake
set(PET_NAME zundamon CACHE STRING "Pet asset directory under pets/")
```

## Python環境

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 学習データの録音

ファームウェアの`record <seconds>`コマンドは、16 kHz、16-bit、モノラルPCMを
USBシリアルへ送信します。標準の録音時間は2秒です。

```powershell
python scripts\record_wav.py COM5 output.wav
python scripts\collect_sample.py COM5 positive
python scripts\collect_sample.py COM5 near_miss
python scripts\collect_sample.py COM5 negative
python scripts\inspect_wav.py samples
```

データセットは次の構成にします。`samples`はGit管理対象外です。

```text
samples/
  positive/
  near_miss/
  negative/
```

## ウェイクワード学習

```powershell
python scripts\train_kws_tiny.py --samples samples --out models\kws_tiny
python scripts\predict_kws_tiny.py `
  --model models\kws_tiny\model_int8.tflite `
  --labels models\kws_tiny\labels.json samples
python scripts\export_kws_dense.py models\kws_tiny\model_int8.tflite
```

`export_kws_dense.py`は学習済みDenseモデルを
`src/kws_model_weights.c`と`include/kws_model_weights.h`へ変換します。

## 音声再生

`tts/test_phrase_16k.wav`は16 kHz、16-bit、モノラルWAVにしてください。
ビルド時に`generate_tts_pcm.py`でファームウェア用PCMへ変換されます。
シリアルから`tts`を入力すると、アニメーションを止めずに再生します。

## scripts

- `pet_spritesheet_to_bins.py`: ペット画像変換
- `record_wav.py`: 任意パスへの録音
- `collect_sample.py`: クラス別学習データ収集
- `inspect_wav.py`: WAV形式と音量の確認
- `train_kws_tiny.py`: RP2350向け軽量KWS学習
- `predict_kws_tiny.py`: 学習済みモデルの評価
- `export_kws_dense.py`: モデル重みのC変換
- `generate_tts_pcm.py`: 16 kHz WAVのC PCM変換
