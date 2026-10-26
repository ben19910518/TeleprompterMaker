# Qt translation sources

These are the editable sources corresponding to the Qt dialog translation catalogs shipped in `src/teleprompter/resources/i18n/`.

- Upstream repository: https://github.com/qt/qttranslations
- Upstream tag: `v6.12.0`
- Upstream files: `translations/qtbase_ja.ts`, `translations/qtbase_zh_CN.ts`
- License selection for this distribution: GPL-3.0-only, under the alternatives in the upstream `licenseRule.json` copied here.
- Copyright: The Qt Company Ltd. and the respective translation contributors. Original names and translator information within the sources are preserved.

Regenerate the QM catalogs using Qt's `lrelease` tool from the installed PySide6 package, for example from the repository root:

```powershell
.\.venv\Lib\site-packages\PySide6\lrelease.exe third_party\qttranslations\qtbase_ja.ts -qm src\teleprompter\resources\i18n\qtbase_ja.qm
.\.venv\Lib\site-packages\PySide6\lrelease.exe third_party\qttranslations\qtbase_zh_CN.ts -qm src\teleprompter\resources\i18n\qtbase_zh_CN.qm
```

See the root LICENSE and THIRD_PARTY_NOTICES.md. These catalogs translate standard Qt dialogs; they are separate from TeleprompterMaker's own UI translation table.
