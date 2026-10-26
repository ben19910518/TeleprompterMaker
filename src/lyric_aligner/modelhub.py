"""Speech-recognition model catalogue and a small resumable downloader.

Models are stored inside the program folder (``<app>/models/<key>``) so the
tool stays portable: copy the whole folder to another PC and the downloaded
model goes with it.
"""
from __future__ import annotations
from teleprompter.i18n import tr

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

from .paths import models_dir

SOURCES = {
    "modelscope": (tr('ModelScope 魔搭（国内推荐）'), "https://www.modelscope.cn/models/{repo}/resolve/master/{file}"),
    "huggingface": (tr('HuggingFace（海外）'), "https://huggingface.co/{repo}/resolve/main/{file}"),
    "hf-mirror": (tr('hf-mirror 镜像'), "https://hf-mirror.com/{repo}/resolve/main/{file}"),
}


@dataclass
class ModelInfo:
    key: str
    title: str
    size_mb: int
    files: list[str]
    repos: dict[str, str] = field(default_factory=dict)
    note: str = ""


MODELS: dict[str, ModelInfo] = {
    "large-v3-turbo": ModelInfo(
        key="large-v3-turbo",
        title=tr('Large-v3 Turbo（推荐，准确）'),
        size_mb=1630,
        files=["config.json", "preprocessor_config.json", "tokenizer.json", "vocabulary.json", "model.bin"],
        repos={
            "modelscope": "pengzhendong/faster-whisper-large-v3-turbo",
            "huggingface": "dropbox-dash/faster-whisper-large-v3-turbo",
            "hf-mirror": "dropbox-dash/faster-whisper-large-v3-turbo",
        },
        note=tr('识别歌声效果最好，CPU 上处理一首歌约 1~3 分钟'),
    ),
    "small": ModelInfo(
        key="small",
        title=tr('Small（较快，准确度一般）'),
        size_mb=490,
        files=["config.json", "tokenizer.json", "vocabulary.txt", "model.bin"],
        repos={
            "modelscope": "pengzhendong/faster-whisper-small",
            "huggingface": "Systran/faster-whisper-small",
            "hf-mirror": "Systran/faster-whisper-small",
        },
        note=tr('体积小、速度快，但歌声识别容易出错'),
    ),
}

DEFAULT_MODEL = "large-v3-turbo"
_UA = {"User-Agent": "Mozilla/5.0 (TeleprompterMaker)"}


def model_path(key: str) -> str:
    return os.path.join(models_dir(), key)


def is_installed(key: str) -> bool:
    info = MODELS.get(key)
    if info is None:
        return False
    d = model_path(key)
    for f in info.files:
        p = os.path.join(d, f)
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            return False
    return os.path.isfile(os.path.join(d, ".complete"))


class DownloadCancelled(Exception):
    pass


ProgressFn = Callable[[int, int, float, str], None]  # done, total, bytes/s, current file


def _content_length(url: str) -> int:
    req = urllib.request.Request(url, headers={**_UA, "Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        cr = r.headers.get("Content-Range")  # bytes 0-0/12345
        if cr and "/" in cr:
            try:
                return int(cr.rsplit("/", 1)[1])
            except ValueError:
                pass
        return int(r.headers.get("Content-Length") or 0)


def download_model(key: str, source: str = "modelscope", progress: Optional[ProgressFn] = None,
                   cancelled: Callable[[], bool] = lambda: False) -> str:
    """Download (or resume) every file of ``key`` from ``source``. Returns the model dir."""
    info = MODELS[key]
    repo = info.repos[source]
    tmpl = SOURCES[source][1]
    dest = model_path(key)
    os.makedirs(dest, exist_ok=True)
    marker = os.path.join(dest, ".complete")
    if os.path.exists(marker):
        os.remove(marker)

    urls = {f: tmpl.format(repo=repo, file=f) for f in info.files}
    sizes = {}
    for f, u in urls.items():
        final = os.path.join(dest, f)
        if os.path.isfile(final) and os.path.getsize(final) > 0 and f != "model.bin":
            sizes[f] = os.path.getsize(final)
            continue
        sizes[f] = _content_length(u)
    total = sum(sizes.values())

    done_before = 0
    t0 = time.time()
    received = 0
    for f in info.files:
        final = os.path.join(dest, f)
        expected = sizes[f]
        if os.path.isfile(final) and (expected <= 0 or os.path.getsize(final) == expected):
            done_before += os.path.getsize(final)
            continue
        part = final + ".part"
        have = os.path.getsize(part) if os.path.isfile(part) else 0
        if expected and have > expected:
            os.remove(part)
            have = 0
        headers = dict(_UA)
        if have:
            headers["Range"] = tr('bytes={p0}-', p0=have)
        req = urllib.request.Request(urls[f], headers=headers)
        with urllib.request.urlopen(req, timeout=60) as r:
            if have and r.status != 206:  # server ignored the range: restart
                have = 0
            mode = "ab" if have else "wb"
            with open(part, mode) as fh:
                last_cb = 0.0
                while True:
                    if cancelled():
                        raise DownloadCancelled()
                    chunk = r.read(1 << 18)
                    if not chunk:
                        break
                    fh.write(chunk)
                    have += len(chunk)
                    received += len(chunk)
                    now = time.time()
                    if progress and now - last_cb > 0.2:
                        last_cb = now
                        speed = received / max(now - t0, 1e-3)
                        progress(done_before + have, total, speed, f)
        if expected and have != expected:
            raise IOError(tr('{p0} 下载不完整（{p1}/{p2} 字节），请重试', p0=f, p1=have, p2=expected))
        os.replace(part, final)
        done_before += have
    if progress:
        progress(total, total, 0.0, "")
    with open(marker, "w", encoding="utf-8") as fh:
        json.dump({"source": source, "repo": repo, "time": time.time()}, fh)
    return dest
