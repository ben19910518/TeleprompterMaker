"""QThread workers so decoding, encoding, recognition and downloads never freeze the UI."""
from __future__ import annotations
from ..i18n import tr

import traceback

from PySide6.QtCore import QThread, Signal

from .. import align, export, media, modelhub


class _Worker(QThread):
    progress = Signal(float, str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def is_cancelled(self) -> bool:
        return self._cancel


class AudioLoadWorker(_Worker):
    loaded = Signal(object, object, object)   # info, pcm (n,2) float32, peaks

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            info = media.probe(self.path)
            pcm = media.decode_audio(self.path, 48000, 2, cancelled=self.is_cancelled)
            pk = media.peaks(pcm, 48000, 100)
            self.loaded.emit(info, pcm, pk)
        except media.DecodeCancelled:
            pass
        except Exception as e:
            self.failed.emit(tr('无法读取音频：{p0}', p0=e))


class ExportWorker(_Worker):
    finished_ok = Signal(object)

    def __init__(self, style, lines, audio_path, out_path, parent=None):
        super().__init__(parent)
        self.style, self.lines, self.audio_path, self.out_path = style, lines, audio_path, out_path

    def run(self):
        try:
            res = export.export_video(self.style, self.lines, self.audio_path, self.out_path,
                                      progress=self.progress.emit, cancelled=self.is_cancelled)
            self.finished_ok.emit(res)
        except export.ExportCancelled:
            self.failed.emit(tr('已取消'))
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(tr('生成失败：{p0}', p0=e))


class AlignWorker(_Worker):
    finished_ok = Signal(object)

    def __init__(self, audio_path, lines, model_key, language, parent=None):
        super().__init__(parent)
        self.audio_path, self.lines, self.model_key, self.language = audio_path, lines, model_key, language

    def run(self):
        try:
            res = align.auto_align(self.audio_path, self.lines, self.model_key, self.language,
                                   progress=self.progress.emit, cancelled=self.is_cancelled)
            self.finished_ok.emit(res)
        except align.AlignCancelled:
            self.failed.emit(tr('已取消'))
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(tr('识别失败：{p0}', p0=e))


class DownloadWorker(_Worker):
    finished_ok = Signal(str)

    def __init__(self, model_key, source, parent=None):
        super().__init__(parent)
        self.model_key, self.source = model_key, source

    def run(self):
        def prog(done, total, speed, fname):
            frac = done / total if total else 0.0
            self.progress.emit(frac, tr('正在下载模型 {p0:.0f}/{p1:.0f} MB  {p2:.1f} MB/s', p0=done / 1000000.0, p1=total / 1000000.0, p2=speed / 1000000.0))
        try:
            path = modelhub.download_model(self.model_key, self.source, prog, self.is_cancelled)
            self.finished_ok.emit(path)
        except modelhub.DownloadCancelled:
            self.failed.emit(tr('已取消下载（再次下载会从断点继续）'))
        except Exception as e:
            self.failed.emit(tr('下载失败：{p0}\n可以换一个下载源再试。', p0=e))


class EncoderProbeWorker(QThread):
    found = Signal(list)

    def run(self):
        names = [n for n in export.ENCODERS if n == "libx264" or export.encoder_available(n)]
        self.found.emit(names)
