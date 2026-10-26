# Third-party notices

The original TeleprompterMaker application code, documentation and original artwork are distributed under **GPL-3.0-only**. See [LICENSE](LICENSE) and [COPYRIGHT](COPYRIGHT). Third-party materials keep their own copyright and license terms; the project license does not replace those terms.

## Materials included in the source repository

### Qt translations 6.12.0

`src/teleprompter/resources/i18n/qtbase_ja.qm` and `qtbase_zh_CN.qm` are compiled Qt translation catalogs, not original TeleprompterMaker translations. Their corresponding editable TS sources are provided in `third_party/qttranslations/`.

Upstream: <https://github.com/qt/qttranslations/tree/v6.12.0>.

Copyright belongs to The Qt Company Ltd. and the respective Qt translation contributors. The upstream module's `licenseRule.json` allows LGPL-3.0-only, GPL-2.0-only, GPL-3.0-only or a Qt commercial license for these module files. This source distribution uses the GPL-3.0-only option. A copy of the original license rule is included alongside the TS files. The GPL text is in the root LICENSE; an LGPL text is retained in LICENSES for reference.

The application's own Chinese/English/Japanese strings are maintained separately in `build_tools/i18n_translations.tsv` and generated into `catalog.json`.

## Runtime dependencies installed separately

The public source repository does not redistribute Python, Qt runtime DLLs, FFmpeg DLLs, CUDA libraries, model weights or fonts. Installing dependencies separately brings in their own license notices and any additional bundled native libraries. The following table is an orientation to the direct dependencies, not a replacement for the license files in each installed distribution.

| Component | Version in requirements | Upstream | License of the named project |
| --- | --- | --- | --- |
| PySide6 / Qt for Python | 6.12.0 | https://code.qt.io/cgit/pyside/pyside-setup.git/ | LGPL-3.0-only / GPL alternatives; see package and module terms |
| PyAV | 19.0.1 | https://github.com/PyAV-Org/PyAV | BSD-3-Clause for PyAV itself; FFmpeg and codecs have separate terms |
| NumPy | 2.5.4 | https://github.com/numpy/numpy | BSD-3-Clause and additional notices for included components |
| faster-whisper | 1.2.1 | https://github.com/SYSTRAN/faster-whisper | MIT |
| CTranslate2 | 4.8.2 | https://github.com/OpenNMT/CTranslate2 | MIT |
| pypinyin | 0.55.0 | https://github.com/mozillazg/python-pinyin | MIT |
| sounddevice | 0.5.6 | https://github.com/spatialaudio/python-sounddevice | MIT; PortAudio has its own permissive notice |

Build tools and transitive dependencies retain their respective terms. In particular, PyInstaller's bootloader exception matters when distributing applications built with it. Recognition models have their own model licenses; no model weights are included here.

## Windows executable distribution status

The pre-existing local v1.3.0 executable ZIP is not included in the initial public source release. Its FFmpeg runtime reports LGPL version 3 or later while the configuration includes x264/x265, and its complete third-party notice/corresponding-source material has not yet been assembled. Choosing GPL for the application does not by itself resolve those binary distribution requirements.

Before publishing a runtime ZIP, inventory the actual packaged DLLs and Python distributions, retain all applicable notices, provide corresponding source and build information as required, and verify the exact FFmpeg/codec build. Reference: <https://ffmpeg.org/legal.html>, <https://github.com/PyAV-Org/pyav-ffmpeg>, <https://doc.qt.io/qt-6/licensing.html>.
