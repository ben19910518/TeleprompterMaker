"""Validate translation templates and write the bundled UTF-8 catalog."""
import ast
import json
import subprocess
from pathlib import Path
from string import Formatter

ROOT = Path(__file__).resolve().parents[1]
catalog = {}
for number, line in enumerate((ROOT/'build_tools/i18n_translations.tsv').read_text('utf-8').splitlines(), 1):
    if not line or line.startswith('#'):
        continue
    parts = line.split('|||')
    if len(parts) != 3:
        raise ValueError(f'Invalid translation row {number}')
    source, en, ja = [value.replace(r'\n', '\n') for value in parts]
    if source in catalog:
        raise ValueError(f'Duplicate source: {source!r}')
    def fields(text):
        return sorted((field, spec, conversion) for _, field, spec, conversion in Formatter().parse(text) if field is not None)
    assert fields(source) == fields(en) == fields(ja), source
    catalog[source] = dict(en=en, ja=ja)

expected = {'提词器视频生成工具'}
for source_file in (ROOT/'src').rglob('*.py'):
    for node in ast.walk(ast.parse(source_file.read_text('utf-8'))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr' and node.args:
            if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                key = node.args[0].value
                if any('\u3400' <= c <= '\u9fff' for c in key):
                    expected.add(key)
missing = expected - catalog.keys()
assert not missing, repr(sorted(missing))
target = ROOT/'src/teleprompter/resources/i18n'
target.mkdir(exist_ok=True)
(target/'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', 'utf-8')
import PySide6
lrelease = Path(PySide6.__file__).parent / ('lrelease.exe' if __import__('os').name == 'nt' else 'lrelease')
for locale in ('zh_CN', 'ja'):
    source = ROOT/'third_party/qttranslations'/('qtbase_'+locale+'.ts')
    subprocess.run([str(lrelease), str(source), '-qm', str(target/('qtbase_'+locale+'.qm'))], check=True)
print(f'{len(catalog)} source strings, English and Japanese complete; Qt dialogs included.')
