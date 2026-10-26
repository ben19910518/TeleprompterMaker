"""Locations of everything the portable program needs.

Frozen (PyInstaller) build: the folder that contains the .exe.
Source checkout: the project root (two levels above this file).
"""
from __future__ import annotations

import os
import shutil
import sys


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def resource_dir() -> str:
    """Bundled read-only resources (icons...)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "teleprompter", "resources")
    return os.path.join(os.path.dirname(__file__), "resources")


def models_dir() -> str:
    override=os.environ.get('LYRIC_ALIGNER_MODELS')
    if override:return os.path.abspath(override)
    pointer=os.path.join(app_dir(),'models.path')
    if os.path.isfile(pointer):
        with open(pointer,encoding='utf-8-sig') as file:
            target=file.read().strip()
        if target:return os.path.abspath(os.path.join(app_dir(),target))
    return os.path.join(app_dir(), "models")


def fonts_dir() -> str:
    return os.path.join(app_dir(), "fonts")


def _writable(d: str) -> bool:
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_test")
        with open(probe, "w") as fh:
            fh.write("x")
        os.remove(probe)
        return True
    except OSError:
        return False


def settings_path() -> str:
    """settings.json next to the exe (portable); %APPDATA% if that folder is read-only."""
    d = app_dir()
    if _writable(d):
        return os.path.join(d, "settings.json")
    alt = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "TeleprompterMaker")
    os.makedirs(alt, exist_ok=True)
    return os.path.join(alt, "settings.json")


_FFMPEG_CACHE: str | None = None


def ffmpeg_exe() -> str:
    """Bundled ffmpeg first, then env override, then PATH."""
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE and os.path.isfile(_FFMPEG_CACHE):
        return _FFMPEG_CACHE
    candidates = [
        os.path.join(app_dir(), "ffmpeg", "ffmpeg.exe"),
        os.path.join(app_dir(), "ffmpeg.exe"),
        os.environ.get("TP_FFMPEG", ""),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            _FFMPEG_CACHE = c
            return c
    found = shutil.which("ffmpeg")
    if found:
        _FFMPEG_CACHE = found
        return found
    raise FileNotFoundError("找不到 ffmpeg.exe，请确认程序目录下的 ffmpeg 文件夹完整。")


def no_window_flags() -> int:
    """creationflags that stop a console window flashing up for child processes."""
    if os.name == "nt":
        return 0x08000000  # CREATE_NO_WINDOW
    return 0
