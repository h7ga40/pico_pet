# OpenJTalk direct WAV synthesis fix update

## Summary

The OpenJTalk project was updated to fix the access violation reported in
`docs/openjtalk_handoff.md`. Direct synthesis from an `.htsvoice` file now
produces a valid WAV instead of crashing while saving the generated waveform.

OpenJTalk commit:

```text
108159c Fix direct OpenJTalk WAV synthesis
```

OpenJTalk project location used for verification:

```text
C:\Users\hi6ak\Documents\OpenJTalk
```

## Root cause and fix

The normal HTS synthesis path generated vocoder output without allocating the
`HTS_GStreamSet.gspeech` sample buffer. `HTS_Engine_save_riff()` later attempted
to read that missing buffer, causing the Windows access violation.

The normal HTS engine now:

- allocates the generated speech sample buffer;
- passes each frame's output area to the vocoder;
- writes the WAV only after synthesis succeeds;
- reports file-open, empty-input, voice-load, and synthesis failures instead of
  continuing into invalid output handling.

The separate raw child-process path was not removed or replaced. It remains
available for RP2350-oriented bounded block processing with
`-raw-block-frames 256`.

## Stable direct interface

`OpenJTalk.exe` now accepts the long-option interface requested by PetApp:

```powershell
C:\Users\hi6ak\Documents\OpenJTalk\x64\Debug\OpenJTalk.exe `
  --dic C:\Users\hi6ak\Documents\OpenJTalk\OpenJTalk\open_jtalk_dic_utf_8-1.11 `
  --voice C:\Users\hi6ak\Documents\OpenJTalk\OpenJTalk\mei\mei_normal.htsvoice `
  --sample-rate 16000 `
  --input input.txt `
  --output output.wav
```

When only `--sample-rate` is supplied, the frame period is scaled from the
voice's original sample rate. For `mei_normal.htsvoice`, 48 kHz / 240 samples is
converted to 16 kHz / 80 samples, preserving the 5 ms frame duration.

The existing short-option command also works:

```powershell
OpenJTalk.exe -x <dic> -m <voice> -s 16000 -ow <output.wav> <input.txt>
```

## PetApp integration options

PetApp's current `scripts/generate_tts_wavs.py` remains compatible and can keep
using the raw export plus child-process sequence. This is the conservative
choice when the raw streaming path is also used to validate RP2350 memory and
block-processing behavior.

The script can now optionally be simplified to one direct OpenJTalk invocation
per phrase:

```python
subprocess.run(
    [
        str(args.open_jtalk),
        "--dic", str(args.dic),
        "--voice", str(args.voice),
        "--sample-rate", "16000",
        "--input", str(text_path),
        "--output", str(wav_path),
    ],
    check=True,
)
```

With this direct form, PetApp no longer needs to export a temporary raw voice or
invoke `hts_engine_raw_cli.exe` solely for offline WAV generation. Keep the WAV
validation already present in `generate_tts_wavs.py`.

## Verification completed

The updated Debug x64 build passed the following checks:

- direct long-option synthesis at 16 kHz;
- direct long-option synthesis at 48 kHz;
- legacy `-s 16000 -ow` synthesis;
- RIFF/WAVE, mono, 16-bit PCM, requested sample rate, and non-empty sample data;
- raw child-process synthesis with `-raw-block-frames 256`;
- invalid voice path returns exit code 1 with a readable diagnostic instead of
  an access violation.

Automated OpenJTalk smoke test:

```powershell
cd C:\Users\hi6ak\Documents\OpenJTalk
python tests\smoke_openjtalk.py
```

## Recommended next step in PetApp

For offline firmware asset generation, switch `generate_tts_wavs.py` to the
direct long-option interface and retain its existing WAV validation. Keep the
current raw implementation in version history or behind an explicit option if
future RP2350 streaming comparisons still require it.
