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

## Windows executable distribution

The v1.3.0 Windows x64 release includes original third-party license/copyright/NOTICE files under `licenses/`, plus source and binary manifests. A companion `TeleprompterMaker_v1.3.0_ThirdPartySources.zip` supplies the application source, version-matched Qt/PySide6/FFmpeg/PyAV/codec sources, build recipes, patches and additional native/Rust dependency sources.

Qt and PySide6 runtime libraries are used under their LGPL-3.0 option; editable translation sources and full corresponding library sources/build information are provided. Users may replace the libraries and rebuild the application/Qt bindings as permitted by those licenses. Original notices and all available upstream license texts are retained; commercial alternatives are not selected by this distribution.

The FFmpeg/x264/x265 binary combination is distributed under GPL-3.0 conditions. The upstream FFmpeg build reports LGPL version 3 or later because its source patch changes the x264/x265 configure classification. That report does not override the GPL terms of the codecs. Exact source, patch, configuration and dependency versions are supplied, with the explanation in `provenance/ffmpeg-runtime.json` in the source attachment.

The package preserves notices for PortAudio, OpenSSL, libffi, SQLite, NumPy/OpenBLAS, Intel OpenMP, GCC runtime libraries/exception, MinGW and Microsoft runtime components. cuDNN, ASIO audio extensions, model weights and fonts are not redistributed in this standard package. Proprietary vendor runtimes remain subject to their own redistribution terms; the application's GPL does not relicense those components.

See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md), `licenses/INDEX.json`, `SOURCE_MANIFEST.json` and the companion source archive for exact files, hashes, provenance and rebuilding instructions. Release downloads: https://github.com/ben19910518/TeleprompterMaker/releases/tag/v1.3.0
