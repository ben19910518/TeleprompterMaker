"""Source-line editing, independent of the renderer's merged display entries."""
from __future__ import annotations
from ..i18n import tr
from .i18n_widgets import QCheckBox, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton

import math
from bisect import bisect_right

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QInputDialog)

from ..lyrics import LyricLine
from .widgets import card, parse_time


def edit_time(value: float) -> str:
    ms = round(value * 1000)
    return tr('{p0:02d}:{p1:02d}.{p2:03d}', p0=ms // 60000, p1=ms // 1000 % 60, p2=ms % 1000)


class LyricEditorMixin:
    def _init_lyric_editor(self):
        self._undo_lyrics = []
        self._redo_lyrics = []
        self._saved_lyrics = ((), False)
        self._lyrics_dirty = False
        self._editor_row = -1

    def _build_lyric_editor(self, layout):
        box, content, head = card(tr('本句微调'))
        box.setToolTip(tr('编辑原始歌词行（不受预览短句合并影响）'))
        self.lyric_editor = box
        self.follow_lyrics = QCheckBox(tr('跟随播放选句'))
        self.follow_lyrics.setChecked(True)
        head.addWidget(self.follow_lyrics)
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        self.editor_start = QLineEdit()
        self.editor_end = QLineEdit()
        self.editor_end.setToolTip(tr('留空表示自动结束；显示的自动时间以空白字段旁的提示为准'))
        self.editor_buttons = []
        self.lyric_nudge_buttons = {}
        for block, (label, field, name, tips) in enumerate(((tr('开始'), self.editor_start, "start", (tr('开头 −'), tr('开头 +'))),
                                                            (tr('结束'), self.editor_end, "end", (tr('结尾 −'), tr('结尾 +'))))):
            col = block * 5
            if block:
                grid.setColumnMinimumWidth(col - 1, 14)
            field.setFixedWidth(104)
            field.setPlaceholderText(tr('分:秒.毫秒'))
            grid.addWidget(QLabel(label), 0, col)
            grid.addWidget(field, 0, col + 1)
            for k, sign in enumerate((-1, 1)):
                for r, milliseconds in enumerate((50, 200)):
                    delta = sign * milliseconds / 1000
                    button = QPushButton(("−" if sign < 0 else "+") + str(milliseconds))
                    button.setObjectName("nudge")
                    button.setToolTip(tr('{p0}{p1}ms', p0=tips[k], p1=milliseconds))
                    button.clicked.connect(lambda checked=False, f=name, d=delta: self._nudge_lyric(f, d))
                    grid.addWidget(button, r, col + 2 + k)
                    self.editor_buttons.append(button)
                    self.lyric_nudge_buttons[(name, sign * milliseconds)] = button
        grid.setColumnStretch(10, 1)
        content.addLayout(grid)
        self.editor_text = QPlainTextEdit()
        self.editor_text.setPlaceholderText(tr('修改歌词，支持原文与翻译分行；应用修改、切换句子或保存时生效'))
        self.editor_text.setFixedHeight(58)
        content.addWidget(self.editor_text)
        row = QHBoxLayout()
        row.setSpacing(6)
        apply = QPushButton(tr('应用修改'))
        apply.setObjectName("accent")
        apply.clicked.connect(self._apply_lyric_fields)
        row.addWidget(apply)
        self.editor_buttons.append(apply)
        for label, callback in ((tr('试听本句'), self._audition_lyric),
                                (tr('此刻设为开始'), lambda: self._stamp_lyric("start")),
                                (tr('此刻设为结束'), lambda: self._stamp_lyric("end"))):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.editor_buttons.append(button)
        row.addStretch(1)
        content.addLayout(row)
        row = QHBoxLayout()
        row.setSpacing(6)
        insert = QPushButton(tr('后插一句'))
        insert.clicked.connect(self._insert_lyric)
        delete = QPushButton(tr('删除本句'))
        delete.clicked.connect(self._delete_lyric)
        self.editor_buttons.append(delete)
        self.btn_lyric_undo = QPushButton(tr('撤销'))
        self.btn_lyric_redo = QPushButton(tr('重做'))
        self.btn_lyric_undo.clicked.connect(lambda: self._history_lyric(False))
        self.btn_lyric_redo.clicked.connect(lambda: self._history_lyric(True))
        self.btn_lyric_save = QPushButton(tr('保存歌词'))
        self.btn_lyric_save.setToolTip(tr('保存到当前歌词文件（Ctrl+S）'))
        self.btn_lyric_save.clicked.connect(self._save_lyrics_current)
        for button in (insert, delete, self.btn_lyric_undo, self.btn_lyric_redo, None, self.btn_lyric_save):
            row.addWidget(button) if button is not None else row.addStretch(1)
        content.addLayout(row)
        self.editor_state = QLabel(tr('请导入歌词；时间为原始歌词时间，不含预览的整体偏移。'))
        self.editor_state.setObjectName("hint")
        self.editor_state.setWordWrap(True)
        content.addWidget(self.editor_state)
        content.addStretch(1)
        layout.addWidget(box)
        self.table.itemSelectionChanged.connect(self._sync_lyric_editor)
        self.table.cellDoubleClicked.connect(lambda *_: self.editor_text.setFocus())
        # Keep typing shortcuts inside text fields native; document undo is scoped to the table.
        for sequence, callback in (("Ctrl+Z", lambda: self._history_lyric(False)),
                                   ("Ctrl+Y", lambda: self._history_lyric(True))):
            shortcut = QShortcut(QKeySequence(sequence), self.table)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(callback)
        save = QShortcut(QKeySequence("Ctrl+S"), self)
        save.activated.connect(self._save_lyrics_current)
        self._sync_lyric_editor()

    def _lyric_state(self):
        return (tuple((line.start, line.end, line.text) for line in self.lines), self.lines_timed)

    def _reset_lyric_history(self, saved=True):
        self._editor_row = -1
        self._undo_lyrics.clear()
        self._redo_lyrics.clear()
        self._saved_lyrics = self._lyric_state() if saved else None
        self._update_lyric_dirty()

    def _update_lyric_dirty(self):
        self._lyrics_dirty = self._lyric_state() != self._saved_lyrics
        self.setWindowModified(self._lyrics_dirty)
        self.btn_lyric_undo.setEnabled(bool(self._undo_lyrics))
        self.btn_lyric_redo.setEnabled(bool(self._redo_lyrics))
        self.btn_lyric_save.setEnabled(bool(self.lines) and self.lines_timed)

    def _selected_lyric(self):
        row = self.table.currentRow()
        return row if 0 <= row < len(self.lines) else -1

    def _effective_lyric_end(self, row):
        line = self.lines[row]
        if line.end is not None:
            return line.end
        if row + 1 < len(self.lines):
            return self.lines[row + 1].start
        return max(line.start + .05, self.audio_info.duration if self.audio_info else line.start + 3)

    def _sync_lyric_editor(self):
        row = self._selected_lyric()
        previous = self._editor_row
        if previous != row and self._editor_has_draft(previous):
            self._editor_row = -1
            if not self._apply_lyric_fields_at(previous, row):
                self._editor_row = previous
                self.table.blockSignals(True)
                self.table.selectRow(previous)
                self.table.blockSignals(False)
                return
            row = self._selected_lyric()
        self._editor_row = row
        active = row >= 0
        for widget in self.editor_buttons + [self.editor_text, self.editor_start, self.editor_end]:
            widget.setEnabled(active)
        if active:
            line = self.lines[row]
            self.editor_start.setText(edit_time(line.start))
            self.editor_end.setText(edit_time(line.end) if line.end is not None else "")
            self.editor_end.setPlaceholderText(edit_time(self._effective_lyric_end(row)) + tr(' 自动'))
            self.editor_text.setPlainText(line.text)
            self.editor_state.setText(tr('第 {p0}/{p1} 句 · ', p0=row + 1, p1=len(self.lines)) +
                                     (tr('未保存修改 · ') if self._lyrics_dirty else "") +
                                     tr('编辑原始时间（不含整体偏移）；句尾留空为自动。'))
        else:
            self.editor_start.clear()
            self.editor_end.clear()
            self.editor_text.clear()
            self.editor_state.setText(tr('请导入或插入歌词；预览合并不会改变这里的原始行。'))
        self._update_lyric_dirty()

    def _editor_error(self, message):
        self.statusBar().showMessage(message, 8000)
        self.editor_state.setText(message)
        return False

    def _validate_lyric_edit(self, lines):
        for i, line in enumerate(lines):
            if not math.isfinite(line.start) or line.start < 0:
                raise ValueError(tr('开始时间必须是非负有限数值。'))
            if not line.text.strip():
                raise ValueError(tr('歌词内容不能为空；删除整句请使用「删除本句」。'))
            nxt = lines[i + 1].start if i + 1 < len(lines) else None
            if nxt is not None and nxt - line.start < .009:
                raise ValueError(tr('开始时间必须按顺序排列，并与下一句至少相隔 10ms。'))
            if line.end is not None:
                if not math.isfinite(line.end) or line.end - line.start < .009:
                    raise ValueError(tr('结束时间必须晚于开始时间至少 10ms。'))
                if nxt is not None and line.end > nxt + .000001:
                    raise ValueError(tr('句尾不能超过下一句开始；请先调整相邻句。'))

    def _commit_lyric_edit(self, lines, row, message):
        try:
            self._validate_lyric_edit(lines)
        except ValueError as exc:
            return self._editor_error(str(exc))
        if tuple((x.start, x.end, x.text) for x in lines) == self._lyric_state()[0]:
            return True
        self._undo_lyrics.append((self._lyric_state(), self._selected_lyric()))
        self._undo_lyrics = self._undo_lyrics[-100:]
        self._redo_lyrics.clear()
        if not self.lines and lines:
            self.lines_timed = True  # A new document starts with a manually specified timestamp.
        self.lines = lines
        self._editor_row = -1
        self.follow_lyrics.setChecked(False)
        self._t_user = True
        self._update_lyric_dirty()
        self._entries_sig = None
        self._rebuild()
        if self.lines:
            self.table.selectRow(min(max(row, 0), len(self.lines) - 1))
        self._sync_lyric_editor()
        self.statusBar().showMessage(message + tr('（尚未保存）'), 6000)
        return True

    def _copy_lyric_lines(self):
        return [LyricLine(x.start, x.end, x.text) for x in self.lines]

    def _apply_lyric_fields(self):
        row = self._selected_lyric()
        return self._apply_lyric_fields_at(row, row)

    def _apply_lyric_fields_at(self, row, selected):
        if row < 0:
            return False
        start = parse_time(self.editor_start.text())
        end_text = self.editor_end.text().strip()
        end = parse_time(end_text) if end_text else None
        if start is None or (end_text and end is None):
            return self._editor_error(tr('时间格式错误，请输入 分:秒.毫秒 或秒数。'))
        lines = self._copy_lyric_lines()
        lines[row] = LyricLine(start, end, self.editor_text.toPlainText().strip())
        return self._commit_lyric_edit(lines, selected, tr('已应用歌词修改'))

    def _flush_lyric_draft(self):
        row = self._editor_row
        if self._editor_has_draft(row):
            return self._apply_lyric_fields_at(row, row)
        return True

    def _nudge_lyric(self, field, delta):
        row = self._selected_lyric()
        if row < 0:
            return
        widget = self.editor_start if field == "start" else self.editor_end
        value = (parse_time(widget.text()) if widget.text().strip() else
                 self._effective_lyric_end(row) if field == "end" else None)
        if value is None or not math.isfinite(value):
            return self._editor_error(tr('请先输入有效时间。'))
        old = widget.text()
        # Do not silently clamp negative times, which would hide an invalid operation.
        value = round(value + delta, 3)
        if value < 0:
            return self._editor_error(tr('时间不能小于零。'))
        widget.setText(edit_time(value))
        if not self._apply_lyric_fields():
            widget.setText(old)

    def _stamp_lyric(self, field):
        if self._selected_lyric() < 0:
            return
        raw_time = self._t - self.style.time_offset
        if raw_time < 0:
            return self._editor_error(tr('扣除整体偏移后时间小于零，不能打点。'))
        widget = self.editor_start if field == "start" else self.editor_end
        old = widget.text()
        widget.setText(edit_time(raw_time))
        if not self._apply_lyric_fields():
            widget.setText(old)

    def _audition_lyric(self):
        row = self._selected_lyric()
        if row >= 0:
            self.follow_lyrics.setChecked(False)
            self.audition(self.lines[row].start + self.style.time_offset,
                          self._effective_lyric_end(row) + self.style.time_offset)

    def _insert_lyric(self):
        if not self._flush_lyric_draft():
            return
        text, ok = QInputDialog.getMultiLineText(self, tr('插入歌词'), tr('新句内容（插入到选中句后）：'))
        if not ok or not text.strip():
            return
        row = self._selected_lyric()
        lines = self._copy_lyric_lines()
        if row < 0:
            row = len(lines) - 1
        start = 0.0
        if row >= 0:
            start = (lines[row].end if lines[row].end is not None else lines[row].start + 1)
            if row + 1 < len(lines):
                lower = lines[row].end if lines[row].end is not None else lines[row].start
                start = round((lower + lines[row + 1].start) / 2, 3)
        lines.insert(row + 1, LyricLine(start, None, text.strip()))
        self._commit_lyric_edit(lines, row + 1, tr('已插入歌词'))

    def _delete_lyric(self):
        if not self._flush_lyric_draft():
            return
        row = self._selected_lyric()
        if row >= 0:
            lines = self._copy_lyric_lines()
            del lines[row]
            self._commit_lyric_edit(lines, row, tr('已删除歌词，可撤销'))

    def _history_lyric(self, redo):
        if not self._flush_lyric_draft():
            return
        source, target = (self._redo_lyrics, self._undo_lyrics) if redo else (self._undo_lyrics, self._redo_lyrics)
        if not source:
            return
        target.append((self._lyric_state(), self._selected_lyric()))
        state, row = source.pop()
        self.lines = [LyricLine(*x) for x in state[0]]
        self._editor_row = -1
        self.lines_timed = state[1]
        self.follow_lyrics.setChecked(False)
        self._t_user = True
        self._update_lyric_dirty()
        self._entries_sig = None
        self._rebuild()
        if self.lines:
            self.table.selectRow(min(max(row, 0), len(self.lines) - 1))
        self._sync_lyric_editor()

    def _confirm_lyric_changes(self):
        if not self._lyrics_dirty and not self._editor_has_draft():
            return True
        answer = QMessageBox.question(self, tr('歌词尚未保存'), tr('是否保存当前歌词的修改？'),
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                      QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        return self._save_lyrics_current() if answer == QMessageBox.StandardButton.Save else True

    def _editor_has_draft(self, row=None):
        if row is None:
            row = self._editor_row
        if not 0 <= row < len(self.lines):
            return False
        line = self.lines[row]
        end = edit_time(line.end) if line.end is not None else ""
        return (self.editor_text.toPlainText() != line.text or self.editor_start.text() != edit_time(line.start)
                or self.editor_end.text() != end)

    def _lyric_row_at_time(self, t):
        if not self.lines or self.renderer is None:
            return -1
        entry_index = self.renderer.current_index(t)
        if not 0 <= entry_index < len(self.renderer.entries):
            return -1
        # Match the timeline's blue entry, including advance/intro timing.
        # A merged entry still contains each original sentence in source order.
        entry = self.renderer.entries[entry_index]
        part = max(0, bisect_right([x.start for x in entry.parts], t - self.style.time_offset) - 1)
        return sum(len(x.parts) for x in self.renderer.entries[:entry_index]) + part

    def _follow_lyric_time(self, t):
        if not self.lines or not self.follow_lyrics.isChecked() or self._editor_has_draft():
            return
        focus = QApplication.focusWidget()
        if focus and (focus is self.table or self.lyric_editor.isAncestorOf(focus)):
            return
        row = self._lyric_row_at_time(t)
        if row >= 0 and row != self.table.currentRow():
            self.table.selectRow(row)
            self.table.scrollToItem(self.table.item(row, 0))
