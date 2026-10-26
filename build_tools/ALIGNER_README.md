# Lyric Aligner

独立应用：`aligner.exe --gui` 打开音频/文本选择及原有时间轴校对界面；也可双击 EXE。

```powershell
aligner.exe --audio vocals.wav --text lyrics.txt --lang ja --out lyrics.lrc --json report.json --enhanced
```

`--models-dir` 指向提词器已有 models 目录，无需重新下载。也可在 exe 旁写 `models.path`，内容是共用 models 的绝对路径或相对路径；环境变量 LYRIC_ALIGNER_MODELS 同样支持。无配置时使用 exe 旁 models。

命令行逐行输出 JSON 进度，成功退出码 0，识别失败 1，取消 130。未安装模型时明确报错，不自动下载大模型。JSON 报告保留识别词、匹配 token 时间、每行可信度和插值标记。增强 LRC 只对逐字可靠匹配且文本一致的行写入时间，不凭空均分生成；全部匹配 token 始终保存在 JSON。

共享核心在 src/lyric_aligner；提词器原 align/modelhub/media 模块只是兼容导入，识别与对齐算法只有一份。GUI 复用提词器现有 AlignDialog。

源码运行：`.venv\Scripts\python.exe LyricAligner.py --help`。
构建：`.venv\Scripts\python.exe -m PyInstaller --noconfirm build_tools\LyricAligner.spec`。
