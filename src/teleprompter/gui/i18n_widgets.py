"""Small Qt adapters retaining translated UI properties, never user data."""
from PySide6 import QtWidgets as W
from PySide6.QtGui import QAction as QtAction
from ..i18n import Text, bind, remembered, render_arg


class Localized:
    _constructor_method = "setText"

    def __init__(self, *args, **kwargs):
        super().__init__(*[render_arg(x) for x in args], **kwargs)
        if args and isinstance(args[0], Text):
            self._localized(self._constructor_method, args[0])

    def _apply_translation(self, method, args):
        return getattr(super(), method)(*[render_arg(x) for x in args])

    def _localized(self, method, *args, key=None):
        bind(self, key or method, method, args)
        return self._apply_translation(method, args)

    def setText(self, text):
        return self._localized("setText", text)

    def setTitle(self, text):
        return self._localized("setTitle", text)

    def setWindowTitle(self, text):
        return self._localized("setWindowTitle", text)

    def setToolTip(self, text):
        return self._localized("setToolTip", text)

    def setStatusTip(self, text):
        return self._localized("setStatusTip", text)

    def setPlaceholderText(self, text):
        return self._localized("setPlaceholderText", text)

    def setSuffix(self, text):
        return self._localized("setSuffix", text)

    def setPrefix(self, text):
        return self._localized("setPrefix", text)


class QLabel(Localized, W.QLabel):
    def setText(self, text):
        # Worker signals pass plain Python strings rather than Text instances.
        return self._localized("setText", remembered(text))


class QPushButton(Localized, W.QPushButton): pass
class QCheckBox(Localized, W.QCheckBox): pass
class QLineEdit(Localized, W.QLineEdit):
    def setText(self, text):
        # File paths and editable time values are content, not interface labels.
        return W.QLineEdit.setText(self, render_arg(text))
class QPlainTextEdit(Localized, W.QPlainTextEdit): pass
class QDoubleSpinBox(Localized, W.QDoubleSpinBox): pass
class QSpinBox(Localized, W.QSpinBox): pass
class QMainWindow(Localized, W.QMainWindow): pass
class QDialog(Localized, W.QDialog): pass
class QMessageBox(Localized, W.QMessageBox): pass
class QAction(Localized, QtAction): pass
class QTableWidgetItem(Localized, W.QTableWidgetItem):
    def _apply_translation(self, method, args):
        table = self.tableWidget()
        blocked = table.blockSignals(True) if table else None
        try:
            return super()._apply_translation(method, args)
        finally:
            if table:
                table.blockSignals(blocked)


class QGroupBox(Localized, W.QGroupBox):
    _constructor_method = "setTitle"


class QMenu(Localized, W.QMenu):
    _constructor_method = "setTitle"


class QComboBox(Localized, W.QComboBox):
    def addItem(self, text, userData=None):
        index = self.count()
        super().addItem(render_arg(text), userData)
        bind(self, ("item", index), "setItemText", (index, text))

    def addItems(self, texts):
        for text in texts:
            self.addItem(text)

    def setItemText(self, index, text):
        return self._localized("setItemText", index, text, key=("item", index))

    def clear(self):
        from ..i18n import _bindings
        entries = _bindings.get(id(self), (None, {}))[1]
        for key in list(entries):
            if isinstance(key, tuple) and key[0] == "item":
                entries.pop(key)
        return super().clear()


class QTableWidget(Localized, W.QTableWidget):
    def setHorizontalHeaderLabels(self, labels):
        return self._localized("setHorizontalHeaderLabels", list(labels))


class QStatusBar(Localized, W.QStatusBar):
    def showMessage(self, text, timeout=0):
        return self._localized("showMessage", remembered(text), timeout)

    def clearMessage(self):
        bind(self, "showMessage", "showMessage", ("", 0))
        return super().clearMessage()
