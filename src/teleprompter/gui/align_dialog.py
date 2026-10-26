"""自动识别时间轴: shared panel (wizard step 1) and the standalone dialog."""
from __future__ import annotations
from ..i18n import tr, is_cancelled_message
from .i18n_widgets import QComboBox, QDialog, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem

import os
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QHeaderView, QProgressBar, QSplitter, QVBoxLayout, QWidget)

from .. import align, modelhub
from ..lyrics import LyricLine, load_lyrics, save_lyrics
from .widgets import card, fmt_time, parse_time
from .workers import AlignWorker, DownloadWorker

WEAK_ROW = QColor("#5a3b1d")


class AlignMixin:
    """Lyric text input, model options, recognition run and result review."""
    apply_text = tr('应用到当前项目')

    def _init_align(self, audio_path: str, texts: list[str], audition: Optional[Callable[[float, float], None]],
                    settings: Optional[dict], import_handler: Optional[Callable[[], None]] = None):
        self.audio_path = audio_path
        self.audition = audition
        self.settings = settings if settings is not None else {}
        self.import_handler = import_handler
        self.worker = None
        self.result: list[align.AlignedLine] = []
        self.saved_path = ""
        self._texts = texts

    def _build_align_ui(self, lay: QVBoxLayout):
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        left, ll, head = card(tr('歌词文本（每行一句）'))
        self.btn_text_import = QPushButton(tr('导入文件…'))
        self.btn_text_import.setToolTip(tr('导入 TXT / LRC / SRT 歌词文件'))
        self.btn_text_import.clicked.connect(self._import_text)
        self.btn_text_paste = QPushButton(tr('粘贴'))
        self.btn_text_paste.setToolTip(tr('用剪贴板中的文字替换左侧歌词'))
        self.btn_text_paste.clicked.connect(self._paste_text)
        self.btn_text_clear = QPushButton(tr('清空'))
        self.btn_text_clear.clicked.connect(lambda: self.text.clear())
        for b in (self.btn_text_import, self.btn_text_paste, self.btn_text_clear):
            b.setObjectName("small")
            head.addWidget(b)
        self.text = QPlainTextEdit("\n".join(self._texts))
        self.text.setPlaceholderText(tr('在这里粘贴或输入歌词，每行一句。\n标题、作者等不唱的行可以删掉，不删也会被自动识别为未演唱。'))
        ll.addWidget(self.text, 1)
        self.text_footer = QVBoxLayout()
        self.text_footer.setContentsMargins(0, 0, 0, 0)
        ll.addLayout(self.text_footer)
        split.addWidget(left)

        right, rl, _ = card(tr('识别结果（双击时间可修改，橙色 = 没听清、时间为估算）'))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", tr('开始'), tr('结束'), tr('歌词'), tr('可信度')])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for c, w in ((0, 40), (1, 80), (2, 80), (4, 60)):
            self.table.setColumnWidth(c, w)
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemChanged.connect(self._cell_edited)
        self.table.cellDoubleClicked.connect(self._row_double)
        rl.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.btn_listen = QPushButton(tr('试听选中行'))
        self.btn_listen.clicked.connect(self._listen)
        self.btn_del = QPushButton(tr('删除选中行'))
        self.btn_del.setToolTip(tr('例如标题、作者这类不唱的行，可以在这里直接删掉'))
        self.btn_del.clicked.connect(self._delete_rows)
        self.btn_lrc = QPushButton(tr('保存为 LRC…'))
        self.btn_lrc.clicked.connect(lambda: self._save("lrc"))
        self.btn_srt = QPushButton(tr('保存为 SRT…'))
        self.btn_srt.clicked.connect(lambda: self._save("srt"))
        for b in (self.btn_listen, self.btn_del, None, self.btn_lrc, self.btn_srt):
            row.addWidget(b) if b is not None else row.addStretch(1)
        rl.addLayout(row)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([400, 640])
        lay.addWidget(split, 1)

        run, cl, _ = card(heading=False)
        opt = QHBoxLayout()
        opt.setSpacing(8)
        opt.addWidget(QLabel(tr('语言')))
        self.lang = QComboBox()
        for name, code in align.LANGUAGES.items():
            self.lang.addItem(tr(name), code or "auto")
        previous = self.settings.get("align_language", align.LANGUAGES.get(self.settings.get("align_lang"), "auto"))
        self.lang.setCurrentIndex(max(0, self.lang.findData(previous or "auto")))
        opt.addWidget(self.lang)
        opt.addSpacing(10)
        opt.addWidget(QLabel(tr('识别模型')))
        self.model = QComboBox()
        for k, m in modelhub.MODELS.items():
            self.model.addItem(tr('{p0}  约{p1}MB', p0=m.title, p1=m.size_mb), k)
        idx = self.model.findData(self.settings.get("align_model", modelhub.DEFAULT_MODEL))
        self.model.setCurrentIndex(max(0, idx))
        self.model.currentIndexChanged.connect(self._update_model_state)
        opt.addWidget(self.model)
        self.model_state = QLabel()
        opt.addWidget(self.model_state)
        self.source_label = QLabel(tr('下载源'))
        opt.addSpacing(10)
        opt.addWidget(self.source_label)
        self.source = QComboBox()
        for k, (title, _) in modelhub.SOURCES.items():
            self.source.addItem(title, k)
        self.source.setCurrentIndex(max(0, self.source.findData(self.settings.get("align_source", "modelscope"))))
        opt.addWidget(self.source)
        self.btn_dl = QPushButton(tr('下载模型'))
        self.btn_dl.clicked.connect(self._download)
        opt.addWidget(self.btn_dl)
        opt.addStretch(1)
        self.btn_cancel = QPushButton(tr('取消'))
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        opt.addWidget(self.btn_cancel)
        self.btn_run = QPushButton(tr('开始识别'))
        self.btn_run.setObjectName("primary")
        self.btn_run.setMinimumWidth(140)
        self.btn_run.clicked.connect(self._run)
        opt.addWidget(self.btn_run)
        cl.addLayout(opt)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        cl.addWidget(self.bar)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        cl.addWidget(self.status)
        lay.addWidget(run)

        self.bottom = QHBoxLayout()
        self.bottom.addStretch(1)
        self.btn_apply = QPushButton(self.apply_text)
        self.btn_apply.setObjectName("primary")
        self.btn_apply.clicked.connect(self._apply)
        self.bottom.addWidget(self.btn_apply)
        lay.addLayout(self.bottom)
        self._set_result_buttons(False)
        self._update_model_state()

    # ---------------------------------------------------------------- input
    def set_audio(self, path: str):
        if path != self.audio_path:
            self.audio_path = path
            self._clear_result()

    def set_texts(self, texts: list[str]):
        if self.worker is None:
            self.text.setPlainText("\n".join(texts))
            self._clear_result()

    def _clear_result(self):
        self.result = []
        self.saved_path = ""
        self._fill_table()
        self._set_result_buttons(False)

    def _import_text(self):
        if self.import_handler is not None:
            return self.import_handler()
        start = os.path.dirname(self.audio_path) if self.audio_path else ""
        fp, _ = QFileDialog.getOpenFileName(self, tr('选择歌词'), start,
                                            tr('歌词/字幕 (*.lrc *.srt *.vtt *.ass *.ssa *.txt);;所有文件 (*.*)'))
        if not fp:
            return
        try:
            doc = load_lyrics(fp)
        except Exception as e:
            QMessageBox.warning(self, tr('歌词'), tr('无法读取歌词文件：{p0}', p0=e))
            return
        self.set_texts([ln.text.replace("\n", " ") for ln in doc.lines])

    def _paste_text(self):
        text = QApplication.clipboard().text()
        if text.strip():
            self.text.setPlainText(text)

    # --------------------------------------------------------------- model
    def _model_key(self) -> str:
        return self.model.currentData()

    def _update_model_state(self):
        ok = modelhub.is_installed(self._model_key())
        self.model_state.setText(tr('✓ 已下载') if ok else tr('未下载'))
        self.model_state.setStyleSheet("color:#5fd39a" if ok else "color:#ffb45c")
        self.btn_dl.setVisible(not ok)
        self.source.setVisible(not ok)
        self.source_label.setVisible(not ok)

    def _download(self):
        if self.worker is not None:
            return
        self.settings["align_source"] = self.source.currentData()
        self.worker = DownloadWorker(self._model_key(), self.source.currentData(), self)
        self.worker.progress.connect(self._progress)
        self.worker.finished_ok.connect(self._download_done)
        self.worker.failed.connect(self._failed)
        self._busy(True)
        self.worker.start()

    def _download_done(self, path):
        self._busy(False)
        self.worker = None
        self.status.setText(tr('模型下载完成。'))
        self._update_model_state()

    # ----------------------------------------------------------------- run
    def _lines(self) -> list[str]:
        return [ln.strip() for ln in self.text.toPlainText().splitlines() if ln.strip()]

    def _run(self):
        if self.worker is not None:
            return
        if not self.audio_path:
            QMessageBox.information(self, tr('自动识别时间轴'), tr('请先选择音频文件。'))
            return
        lines = self._lines()
        if not lines:
            QMessageBox.warning(self, tr('没有歌词'), tr('请先在左边输入歌词，每行一句。'))
            return
        if not modelhub.is_installed(self._model_key()):
            r = QMessageBox.question(self, tr('需要下载模型'),
                                     tr('第一次使用需要下载识别模型，现在下载吗？\n（下载一次即可，之后可离线使用）'))
            if r == QMessageBox.StandardButton.Yes:
                self._download()
            return
        self.settings["align_language"] = self.lang.currentData()
        self.settings["align_model"] = self._model_key()
        self.worker = AlignWorker(self.audio_path, lines, self._model_key(),
                                  None if self.lang.currentData() == "auto" else self.lang.currentData(), self)
        self.worker.progress.connect(self._progress)
        self.worker.finished_ok.connect(self._align_done)
        self.worker.failed.connect(self._failed)
        self._busy(True)
        self.worker.start()

    def _cancel(self):
        if self.worker is not None:
            self.worker.cancel()
            self.status.setText(tr('正在取消…'))

    def _busy(self, on: bool):
        for w in (self.btn_run, self.btn_dl, self.model, self.lang, self.text, self.source,
                  self.btn_text_import, self.btn_text_paste, self.btn_text_clear):
            w.setEnabled(not on)
        self.btn_cancel.setEnabled(on)
        if not on:
            self.bar.setValue(0)

    def _progress(self, frac: float, msg: str):
        self.bar.setValue(int(frac * 1000))
        self.status.setText(msg)

    def _failed(self, msg: str):
        self._busy(False)
        self.worker = None
        self.status.setText(msg)
        if not is_cancelled_message(msg):
            QMessageBox.warning(self, tr('出错了'), msg)
        self._update_model_state()

    def _align_done(self, res):
        self._busy(False)
        self.worker = None
        self.result = res
        self.saved_path = ""
        self._fill_table()
        weak = sum(1 for r in res if r.interpolated or r.score < 0.5)
        self.status.setText(tr('完成：共 {p0} 行', p0=len(res)) + (tr('，其中 {p0} 行没听清（橙色），请检查。', p0=weak) if weak else tr('，全部识别成功。')))
        self._set_result_buttons(True)

    # --------------------------------------------------------------- table
    def _fill_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.result))
        for i, r in enumerate(self.result):
            items = [QTableWidgetItem(str(i + 1)), QTableWidgetItem(fmt_time(r.start)),
                     QTableWidgetItem(fmt_time(r.end)), QTableWidgetItem(r.text),
                     QTableWidgetItem(tr('估算') if r.interpolated else tr('{p0}%', p0=int(r.score * 100)))]
            for c, it in enumerate(items):
                if c in (0, 3, 4):
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if r.interpolated or r.score < 0.5:
                    it.setBackground(WEAK_ROW)
                    it.setToolTip(tr('这一行没有听清楚，时间是根据前后估算的，建议试听确认。'))
                self.table.setItem(i, c, it)
        self.table.blockSignals(False)

    def _cell_edited(self, item: QTableWidgetItem):
        row, col = item.row(), item.column()
        if row >= len(self.result) or col not in (1, 2):
            return
        v = parse_time(item.text())
        r = self.result[row]
        self.table.blockSignals(True)
        if v is None:
            item.setText(fmt_time(r.start if col == 1 else r.end))
        else:
            if col == 1:
                r.start = v
            else:
                r.end = v
            r.interpolated = False
            r.score = max(r.score, 1.0)
            item.setText(fmt_time(v))
            for c in range(5):
                it = self.table.item(row, c)
                if it is not None:
                    it.setBackground(QColor(0, 0, 0, 0))
            self.table.item(row, 4).setText(tr('手动'))
        self.table.blockSignals(False)

    def _row_double(self, row: int, col: int):
        if col in (0, 3, 4):
            self._listen()

    def _listen(self):
        rows = sorted({i.row() for i in self.table.selectedItems()})
        if not rows or not self.result or self.audition is None:
            return
        r0, r1 = self.result[rows[0]], self.result[rows[-1]]
        self.audition(r0.start, r1.end)

    def _delete_rows(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        if not rows:
            return
        for r in rows:
            if 0 <= r < len(self.result):
                del self.result[r]
        self._fill_table()
        self.status.setText(tr('已删除 {p0} 行，剩余 {p1} 行。', p0=len(rows), p1=len(self.result)))

    # -------------------------------------------------------------- output
    def _set_result_buttons(self, on: bool):
        for b in (self.btn_lrc, self.btn_srt, self.btn_apply, self.btn_listen, self.btn_del):
            b.setEnabled(on)

    def lyric_lines(self) -> list[LyricLine]:
        out = []
        for r in sorted(self.result, key=lambda x: x.start):
            out.append(LyricLine(float(r.start), float(r.end) if r.end > r.start else None, r.text))
        return out

    def _save(self, kind: str):
        base = os.path.splitext(self.audio_path)[0] + "." + kind
        path, _ = QFileDialog.getSaveFileName(self, tr('保存歌词'), base,
                                              tr('LRC 歌词 (*.lrc)') if kind == "lrc" else tr('SRT 字幕 (*.srt)'))
        if not path:
            return
        save_lyrics(self.lyric_lines(), path)
        self.status.setText(tr('已保存：{p0}', p0=path))
        self.saved_path = path

    def _apply(self):
        self.applied.emit(self.lyric_lines())
        self.status.setText(tr('已应用到当前项目。'))

    def cancel_worker(self, ask: bool = True) -> bool:
        if self.worker is None:
            return True
        if ask and QMessageBox.question(self, tr('正在处理'), tr('正在处理中，确定要取消并关闭吗？')) != QMessageBox.StandardButton.Yes:
            return False
        self.worker.cancel()
        self.worker.wait(5000)
        self.worker = None
        return True


class AlignPanel(AlignMixin, QWidget):
    """Step 1 of the main window: lyric input and automatic timing in place."""
    applied = Signal(list)       # list[LyricLine]
    apply_text = tr('应用并进入下一步 →')

    def __init__(self, parent=None, audition=None, settings=None, import_handler=None):
        super().__init__(parent)
        self._init_align("", [], audition, settings, import_handler)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self._build_align_ui(lay)


class AlignDialog(AlignMixin, QDialog):
    applied = Signal(list)       # list[LyricLine]

    def __init__(self, parent, audio_path: str, texts: list[str],
                 audition: Optional[Callable[[float, float], None]] = None, settings: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle(tr('自动识别时间轴'))
        self.resize(1120, 720)
        self._init_align(audio_path, texts, audition, settings)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        intro = QLabel(
            tr('把歌词按「一行一句」粘贴或修改在左边（标题、作者等不唱的行可以删掉，不删也会被自动识别为未演唱），然后点「开始识别」。程序会听歌并给每一行配上时间，结果可以在右侧检查和修改。'))
        intro.setWordWrap(True)
        intro.setObjectName("hint")
        lay.addWidget(intro)
        lay.addWidget(QLabel(tr('音频：{p0}', p0=os.path.basename(audio_path))))
        self._build_align_ui(lay)
        close = QPushButton(tr('关闭'))
        close.clicked.connect(self.reject)
        self.bottom.addWidget(close)

    def _apply(self):
        super()._apply()
        self.accept()

    def reject(self):
        if self.cancel_worker():
            super().reject()
