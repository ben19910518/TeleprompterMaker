"""UI language selection and deferred, parameter-safe translations."""
from __future__ import annotations

import json
import weakref
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLocale, QObject, QTranslator, Signal
import shiboken6


def resolve_language(preference="auto", system_name=None):
    if preference in ("zh", "en", "ja"):
        return preference
    system = QLocale.system()
    name = system_name if system_name is not None else (system.uiLanguages() or [system.name()])[0]
    code = name.replace("-", "_").split("_")[0].lower()
    return code if code in ("zh", "en", "ja") else "en"


_language = resolve_language()
_catalog = None
_bindings = {}
_rendered = OrderedDict()
_qt_translator = None


def _translations():
    global _catalog
    if _catalog is None:
        from .paths import resource_dir
        _catalog = json.loads((Path(resource_dir()) / "i18n" / "catalog.json").read_text("utf-8"))
    return _catalog


def language():
    return _language


class Text(str):
    """A string which retains its source and parameters for live language changes."""
    def __new__(cls, source, **params):
        obj = super().__new__(cls, _format(source, params))
        obj.source, obj.params = source, params
        _rendered[str(obj)] = obj
        if len(_rendered) > 4096:
            _rendered.popitem(last=False)
        return obj

    def render(self):
        return _format(self.source, self.params)

    def __add__(self, other):
        return Text("{p0}{p1}", p0=self, p1=other)

    def __radd__(self, other):
        return Text("{p0}{p1}", p0=other, p1=self)


def _format(source, params):
    translated = source if _language == "zh" else _translations().get(source, {}).get(_language, source)
    values = {key: value.render() if isinstance(value, Text) else value for key, value in params.items()}
    return translated.format(**values) if params else translated


def tr(source, **params):
    return source if isinstance(source, Text) and not params else Text(source, **params)


def join_text(separator, values):
    result = ""
    for value in values:
        result = Text("{p0}{p1}{p2}", p0=result, p1=separator if result else "", p2=value)
    return result


def remembered(value):
    return value if isinstance(value, Text) else _rendered.get(value, value)


def is_cancelled_message(value):
    source = remembered(value)
    if isinstance(source, Text):
        return source.source.startswith("已取消")
    prefixes = ["已取消"]
    for key, translations in _translations().items():
        if key.startswith("已取消"):
            prefixes.extend(translations.values())
    return any(str(value).startswith(prefix) for prefix in prefixes)


def bind(owner, key, method, args):
    owner_id = id(owner)
    if owner_id not in _bindings:
        _bindings[owner_id] = (weakref.ref(owner, lambda ref, ident=owner_id: _bindings.pop(ident, None)), {})
    entries = _bindings[owner_id][1]
    if any(isinstance(arg, Text) or isinstance(arg, list) and any(isinstance(x, Text) for x in arg) for arg in args):
        entries[key] = (method, args)
    else:
        entries.pop(key, None)


def render_arg(value):
    if isinstance(value, Text):
        return value.render()
    if isinstance(value, list):
        return [render_arg(x) for x in value]
    return value


class LanguageEvents(QObject):
    changed = Signal(str)


events = LanguageEvents()


def set_language(preference):
    global _language, _qt_translator
    _language = resolve_language(preference)
    app = QCoreApplication.instance()
    if app is not None:
        if _qt_translator is not None:
            app.removeTranslator(_qt_translator)
        _qt_translator = None
        if _language in ("zh", "ja"):
            from .paths import resource_dir
            translator = QTranslator(app)
            suffix = "zh_CN" if _language == "zh" else "ja"
            if translator.load(str(Path(resource_dir()) / "i18n" / ("qtbase_" + suffix + ".qm"))):
                app.installTranslator(translator)
                _qt_translator = translator
    for owner_id, (ref, entries) in list(_bindings.items()):
        owner = ref()
        if owner is None or not shiboken6.isValid(owner):
            _bindings.pop(owner_id, None)
            continue
        was_blocked = owner.blockSignals(True) if hasattr(owner, "blockSignals") else None
        try:
            for method, args in list(entries.values()):
                owner._apply_translation(method, args)
        finally:
            if was_blocked is not None:
                owner.blockSignals(was_blocked)
    events.changed.emit(_language)
    return _language
