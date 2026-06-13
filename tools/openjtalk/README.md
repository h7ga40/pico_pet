# Bundled OpenJTalk executable

`OpenJTalk.exe` is a Windows x64 Debug build used to generate offline WAV
assets for PetApp.

- Upstream project: https://open-jtalk.sourceforge.net/
- Local OpenJTalk fix commit: `108159c Fix direct OpenJTalk WAV synthesis`
- SHA-256: `BB97F2375BA56F1744A5976F5E406B0856BD0FED90DBB43AAC7315C4728EC7A2`
- License: Modified BSD (`BSD-3-Clause`); see `LICENSE.txt`

The Open JTalk dictionary and HTS voice are separate distributions and are not
included here.

- Dictionary: download `open_jtalk_dic_utf_8-1.11.tar.gz` from
  https://sourceforge.net/projects/open-jtalk/
- Mei voice: download `MMDAgent_Example-1.8.zip` from
  https://sourceforge.net/projects/mmdagent/ and extract `mei_normal.htsvoice`
  from the archive.

Extract the downloaded files and place them at these repository-relative paths:

```text
tools\openjtalk\open_jtalk_dic_utf_8-1.11\
tools\openjtalk\mei\mei_normal.htsvoice
```

Override these locations with `--dic` and `--voice` when necessary.
