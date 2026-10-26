# -*- mode: python ; coding: utf-8 -*-
# Build:  .venv\Scripts\python.exe -m PyInstaller --noconfirm build_tools\TeleprompterMaker.spec
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")

datas = [(os.path.join(SRC, "teleprompter", "resources"), os.path.join("teleprompter", "resources"))]
datas += collect_data_files("faster_whisper")
datas += collect_data_files("pypinyin")
binaries = collect_dynamic_libs("ctranslate2")

a = Analysis(
    [os.path.join(ROOT, "LyricAligner.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=["sounddevice", "PySide6.QtNetwork", "lyric_aligner.cli", "lyric_aligner.gui", "teleprompter.gui.align_dialog", "faster_whisper", "pypinyin", "ctranslate2"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["onnxruntime", "hf_xet", "tkinter", "_tkinter", "PIL", "IPython", "pytest", "matplotlib",
              "scipy", "pandas", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtWebEngineCore", "PySide6.QtPdf", "PySide6.QtOpenGL"],
    noarchive=False,
)
# software OpenGL fallback (~20 MB): this app paints with QPainter only
a.binaries = [b for b in a.binaries if os.path.basename(b[0]).lower() not in ("opengl32sw.dll","icuuc.dll","icudt78.dll")]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="aligner",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=os.path.join(SRC, "teleprompter", "resources", "icon.ico"),
    version=os.path.join(ROOT, "build_tools", "version_info.txt"),
)
gui_exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name="LyricAligner",debug=False,strip=False,upx=False,console=False,icon=os.path.join(SRC,"teleprompter","resources","icon.ico"))
coll = COLLECT(exe, gui_exe, a.binaries, a.datas, strip=False, upx=False, name="aligner")
