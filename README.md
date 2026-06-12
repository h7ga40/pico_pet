# Pico Pet

[RP2350 Touch AMOLED](https://www.waveshare.com/RP2350-Touch-AMOLED-1.8.htm)に Codex Pet の `spritesheet.webp` を利用して、OLEDに表示するアプリ。

`pets/zundamon`のフォルダに下記からダウンロードした`spritesheet.webp`を入れてください。

<https://codex-pet.org/pets/zundamon/>

別のスプライトを使用したい場合は、`pets`フォルダに適当な名前でフォルダを作り`spritesheet.webp`を入れ、`CMakeLists.txt`の下記の部分のフォルダ名を書き換えてください。

```camke
set(PET_NAME zundamon CACHE STRING "Pet asset directory under pets/")
```

## 準備

スプライトを取り込むためにPythonスクリプトを実行しています。PythonスクリプトはPillowモジュールを使っているので、インストールする必要があります。

```powershell
python3 -m venv .venv
.venv\Scripts\activate.ps1
pip install -r requirements.txt
```

CMakeで使うPythionをvenvの環境で実行するため`.vscode/cmake-kits.json`を編集する必要があります。`Python3_EXECUTABLE`の値を下記のように変更してください。

```json
"Python3_EXECUTABLE": "${workspaceFolder}/.venv/Scripts/python.exe"
```

## ウェイクワード学習ツール

学習用WAVは16 kHz、16-bit、モノラルで用意します。データセットは次の構成です。

```text
samples/
  positive/
  negative/
  near_miss/
```

RP2350向けの小型モデルは次のコマンドで学習・確認・C配列化できます。

```powershell
python scripts/train_kws_tiny.py --samples samples --out models/kws_tiny
python scripts/predict_kws_tiny.py --model models/kws_tiny/model_int8.tflite `
  --labels models/kws_tiny/labels.json samples/positive/example.wav
python scripts/tflite_to_c_array.py models/kws_tiny/model_int8.tflite
```

ログメル特徴量モデルには`train_kws_logmel.py`、通常のKerasモデルには
`train_kws.py`を使用します。`test_speech_features.py`はPython側の16 kHz特徴量計算を
固定テストデータと比較します。

`record_wav.py`と`collect_sample.py`は、デバイス側のPCM転送コマンドを追加する段階で
使用します。現在のファームウェアはまだPCM転送コマンドを実装していません。
