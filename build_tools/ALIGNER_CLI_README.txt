Lyric Aligner 命令行版使用说明

一、确认结果
aligner.exe 是命令行入口，LyricAligner.exe 是图形界面入口，两者共用 _internal、cuda 和 models。命令行入口已使用包内模型完成实际推理检查，并确认启用了显卡加速。
以下示例适用于 Windows PowerShell，先进入软件目录。无需 Python 或启动脚本。

二、最常用命令
查看参数：
.\aligner.exe --help

输入音频和歌词，生成普通 LRC：
.\aligner.exe --audio "D:\Music\song.wav" --text "D:\Music\song.txt" --lang zh --out "D:\Music\song.lrc"

同时生成详细 JSON 报告：
.\aligner.exe --audio "D:\Music\song.mp3" --text "D:\Music\song.txt" --lang ja --out "D:\Music\song.lrc" --json "D:\Music\song.report.json"

请求增强 LRC：
.\aligner.exe --audio "D:\Music\song.wav" --text "D:\Music\song.txt" --lang zh --out "D:\Music\song.enhanced.lrc" --json "D:\Music\song.report.json" --enhanced

路径包含空格时必须保留双引号。歌词文件为 UTF-8 TXT，可带 BOM，每行一句，不要带已有时间标签。音频和歌词的演唱顺序应一致。输出目录会自动创建；已有输出文件会被覆盖。

三、参数说明
--audio 路径       输入音频。
--text 路径        输入歌词 TXT。
--out 路径         输出 LRC；命令行始终写 LRC，不会根据扩展名切换格式。
--json 路径        可选，输出完整 JSON 报告。
--lang 语言        默认 auto；可用 auto、zh、yue、ja、en、ko 等 Whisper 语言代码。歌词语言明确时建议显式指定。
--model 名称       默认 large-v3-turbo，包内已带。small 未附带，不会由命令行自动下载。
--models-dir 路径  可选，模型根目录；目录下应有 large-v3-turbo 子目录，而非直接指向 model.bin。
--no-refine        跳过对漏句的补充识别，可缩短处理；默认会尝试补识别。
--enhanced         尝试输出带 <分:秒.百分秒> 字符时间的增强 LRC。仅当匹配 token 数量及文本与原行完全一致时才写逐字时间，其余行保留普通 LRC；不是每行都有逐字时间。JSON 中仍保留匹配 token 详情。
--gui              打开图形界面，可配合 --audio 和 --text 预填输入。
--help / -h        显示帮助。
--smoke-test       内部界面自检参数，普通使用不需要。

命令行处理时 --audio、--text、--out 三个参数必须同时提供。无参数运行会打开图形界面。
命令行没有单独的 GPU 开关，自动尝试 NVIDIA GPU，失败时回退 CPU。也没有命令行 SRT 导出参数；需要 SRT 请用图形界面的“保存为 SRT…”。

四、模型路径优先级
1. --models-dir（本次运行设置环境变量）。
2. 环境变量 LYRIC_ALIGNER_MODELS。
3. EXE 旁的 models.path（相对路径以 EXE 所在目录为基准）。
4. EXE 旁的 models 目录。
本包 models.path 已设置为 models，复制整个文件夹即可沿用。
自定义模型根目录示例：
.\aligner.exe --audio "D:\Music\song.wav" --text "D:\Music\song.txt" --out "D:\Music\song.lrc" --models-dir "E:\SharedModels"
此时应存在 E:\SharedModels\large-v3-turbo\model.bin 等完整文件及 .complete。

五、进度、报告和退出码
标准输出逐行发送 JSON：
{"event":"progress","progress":0.05,"message":"正在识别歌声（显卡加速）…"}
{"event":"done","out":"完整输出路径","report":"报告路径或 null"}
progress 为 0~1 的总体进度；message 出现“显卡加速”表示实际选用了 CUDA；出现“CPU”表示回退 CPU。
运行失败时错误 JSON 写入标准错误，event 为 error，message 为错误说明。
退出码：0 成功；1 识别/文件处理失败；2 命令行参数错误；130 捕获到键盘中断（Ctrl+C）。外部强制终止进程的退出码可能不同。
PowerShell 可在命令后查看：
$LASTEXITCODE

JSON 报告主要字段：
schema_version：报告格式版本。
audio、model、elapsed：音频路径、模型名称、处理耗时（秒）。
language、duration：识别语言、音频时长（秒）。
lines：每行歌词的 text、start、end、score、interpolated。
words：模型识别出的词及 start/end/prob。
tokens：已匹配到歌词的 token，含 line（从 0 开始）、text、start、end、score。
start/end 均为秒。interpolated=true 表示该行时间经过估算，建议人工复核。score 是算法匹配分数，不是准确率保证。命令行不会自动清理标题、作者等非演唱文本。

六、批量处理（PowerShell 中直接执行）
约定同一目录每首音频都有同名 TXT，例如 song.mp3 和 song.txt：
$musicDir = "D:\Music"
Get-ChildItem -LiteralPath $musicDir -Filter *.mp3 | ForEach-Object {
    $audioFile = $_.FullName
    $textFile = [IO.Path]::ChangeExtension($audioFile, ".txt")
    $lrcFile = [IO.Path]::ChangeExtension($audioFile, ".lrc")
    $reportFile = [IO.Path]::ChangeExtension($audioFile, ".report.json")
    if (Test-Path -LiteralPath $textFile) {
        & .\aligner.exe --audio $audioFile --text $textFile --lang zh --out $lrcFile --json $reportFile
        if ($LASTEXITCODE -ne 0) { Write-Warning "处理失败：$audioFile" }
    } else {
        Write-Warning "跳过，缺少歌词：$textFile"
    }
}
此示例逐首处理，避免多进程同时加载模型占满显存。每首歌会重新启动进程并加载模型。已有同名 LRC 和 JSON 会覆盖，请先备份需要保留的输出。
