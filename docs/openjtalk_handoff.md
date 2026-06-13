# OpenJTalk integration handoff

## Purpose

PetApp currently uses pre-generated WAV files as a temporary TTS implementation.
Each non-empty, non-comment line in `tts/input.txt` becomes one 16 kHz WAV file.
The WAV files are embedded in the RP2350 firmware and one phrase is selected at
random when a wakeword is detected.

The following functions were confirmed together on the device:

- AMOLED pet animation
- wakeword detection
- non-blocking WAV playback
- random phrase playback after wakeword detection

## OpenJTalk location used for testing

The tools were used from a separate Codex project:

```text
C:\Users\hi6ak\Documents\OpenJTalk
```

Relevant files:

```text
x64\Debug\OpenJTalk.exe
x64\Debug\hts_engine_cli.exe
x64\Debug\hts_engine_raw_cli.exe
OpenJTalk\open_jtalk_dic_utf_8-1.11
OpenJTalk\mei\mei_normal.htsvoice
```

## Problem found

Direct synthesis with the normal HTS voice path crashed with Windows exit code
`0xC0000005` (`3221225477`).

Example command shape:

```powershell
OpenJTalk.exe `
  -x OpenJTalk\open_jtalk_dic_utf_8-1.11 `
  -m OpenJTalk\mei\mei_normal.htsvoice `
  -s 16000 `
  -ow output.wav `
  input.txt
```

The crash occurred during synthesis before a usable WAV was produced. The
front-end plus raw child-process path worked, so the dictionary and input text
were usable.

## Working 16 kHz path

The existing `mei_normal.raw` was a 48 kHz profile. Using it directly produced a
valid 48 kHz WAV, which is not suitable for PetApp. The successful sequence was:

1. Export a temporary 16 kHz raw voice from `mei_normal.htsvoice`.
2. Run `OpenJTalk.exe` as the front end with `hts_engine_raw_cli.exe` as the raw
   synthesis child.
3. Validate that the resulting WAV is mono, 16-bit, and 16 kHz.

Equivalent commands:

```powershell
hts_engine_cli.exe export-voice `
  --voice OpenJTalk\mei\mei_normal.htsvoice `
  --output voice_16k.raw `
  --tts-16khz

OpenJTalk.exe `
  -x OpenJTalk\open_jtalk_dic_utf_8-1.11 `
  -raw voice_16k.raw `
  -raw-engine x64\Debug\hts_engine_raw_cli.exe `
  -raw-block-frames 256 `
  -ow output.wav `
  input.txt
```

PetApp automates this sequence in `scripts/generate_tts_wavs.py`. The temporary
raw voice is created once per invocation and reused for every input line.

## PetApp usage

Edit `tts/input.txt`, one phrase per line. Empty lines and lines beginning with
`#` are ignored.

```powershell
python scripts\generate_tts_wavs.py
```

Outputs:

```text
tts/generated/phrase_000.wav
tts/generated/phrase_001.wav
...
```

On the next CMake build, `scripts/generate_tts_pcm.py` combines all generated
WAV files into an embedded PCM phrase table. OpenJTalk is not required during a
normal firmware build as long as the generated WAV files are present.

## Requested OpenJTalk follow-up

1. Reproduce and fix the `OpenJTalk.exe -m ... -ow ...` access violation.
2. Add a stable command that directly writes a requested sample rate, especially
   16 kHz, without requiring callers to assemble the raw export sequence.
3. Keep the current raw child-process path available because it is working and
   supports bounded block processing with `-raw-block-frames 256`.
4. Return a clear diagnostic instead of crashing when the normal synthesis path
   cannot initialize or process a voice.
5. Add an automated smoke test that synthesizes a short UTF-8 Japanese input and
   verifies RIFF/WAVE, mono, 16-bit, and the requested sample rate.

## Expected interface for future integration

A convenient stable interface for PetApp would be equivalent to:

```powershell
OpenJTalk.exe --dic <dir> --voice <file> --sample-rate 16000 `
  --input <utf8.txt> --output <wav>
```

It should exit nonzero with a readable error on failure and produce a mono,
16-bit, 16 kHz WAV on success. PetApp can continue handling one input line per
process or use a batch option if OpenJTalk later provides one.
