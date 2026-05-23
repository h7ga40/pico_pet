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
