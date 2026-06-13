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
USBシリアルへ送信します。

```powershell
python scripts\record_wav.py COM5 output.wav
python scripts\collect_sample.py COM5 positive
python scripts\collect_sample.py COM5 near_miss
python scripts\collect_sample.py COM5 negative
python scripts\collect_sample.py COM5 noise
python scripts\inspect_wav.py samples
```

連続収録では、まず10秒録音から音量のある部分を2秒で切り出し、
`samples/unclassified`へ保存します。

```powershell
python scripts\collect_unclassified.py COM5
```

しきい値は正規化RMSです。小さな音を拾わない場合は下げ、ノイズを拾いすぎる場合は
上げてください。

```powershell
python scripts\collect_unclassified.py COM5 --threshold 0.008
```

## STT分類

PC側のローカルSTTを使う場合は追加依存関係を導入します。初回実行時は
faster-whisperのモデルがダウンロードされます。

```powershell
pip install -r requirements-stt.txt
python scripts\classify_samples_stt.py "ずんだもん" --model small
```

`unclassified`内のWAVは、STT結果に対象語が含まれれば`positive`、類似していれば
`near_miss`、その他は`negative`へ移動します。認識できないWAVは未分類に残ります。
分類結果は`samples/metadata.csv`へ記録されるため、学習前に確認してください。
ファイル名は`ずんだもん_00001.wav`のようにSTTの認識結果と5桁連番で保存されます。
Windowsで使えない記号は自動的に置換されます。誤分類を直す場合は、
ファイル名を変更せず正しいクラスのフォルダへ移動して構いません。

```text
samples/
  unclassified/
  positive/
  near_miss/
  negative/
  noise/
  metadata.csv
```

`samples`はGit管理対象外です。
`noise`は無音や環境音を保存するフォルダです。学習時には`negative`へ統合され、
ファームウェアの3クラス構成を変えずに誤検出を抑えるデータとして使われます。
クラスごとのサンプル数に差がある場合は、学習時にクラス重みを自動調整します。

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

`tts/input.txt`の空行とコメント以外の各行から、16 kHz、16-bit、モノラルWAVを
1つずつ生成します。Open JTalkを用意したPCで次を実行してください。

```powershell
python scripts\generate_tts_wavs.py
```

生成された`tts/generated/phrase_*.wav`は、ビルド時に`generate_tts_pcm.py`で
ファームウェア用PCMテーブルへ変換されます。ウェイクワード検出時とシリアルの
`tts`コマンド実行時に、いずれか1つをランダムに選び、アニメーションを止めずに再生します。

## scripts

- `pet_spritesheet_to_bins.py`: ペット画像変換
- `record_wav.py`: 任意パスへの録音
- `collect_sample.py`: クラスを指定した単発収録
- `collect_unclassified.py`: 音量区間の連続収録
- `classify_samples_stt.py`: 未分類WAVのSTT分類
- `inspect_wav.py`: WAV形式と音量の確認
- `train_kws_tiny.py`: RP2350向け軽量KWS学習
- `predict_kws_tiny.py`: 学習済みモデルの評価
- `export_kws_dense.py`: モデル重みのC変換
- `generate_tts_pcm.py`: 16 kHz WAVのC PCM変換
- `generate_tts_wavs.py`: `input.txt`からOpen JTalk WAVを一括生成
