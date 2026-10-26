# Teleprompter Maker v1.3.0

Windows 提词器视频生成工具，采用 **GPL-3.0-only** 开源。

## 下载

- **普通用户**：[下载 Windows x64 绿色包](https://github.com/ben19910518/TeleprompterMaker/releases/download/v1.3.0/TeleprompterMaker_v1.3.0_Windows_x64.zip)。完整解压后运行 `TeleprompterMaker.exe`，不需要安装 Python 或启动脚本。
- **开发者与再分发者**：[配套源码、许可与重建资料](https://github.com/ben19910518/TeleprompterMaker/releases/download/v1.3.0/TeleprompterMaker_v1.3.0_ThirdPartySources.zip)。包含应用源码、221 份上游源码归档、原始构建脚本/补丁和校验清单。
- 两个附件均提供同名 `.sha256` 校验文件。GitHub 自动生成的 Source code 附件不含 EXE。

## 功能

- 两步界面：导入与对轴、格式与微调。
- 导入 LRC/SRT，或对纯文本歌词自动对轴，支持模型下载、结果可信度检查与试听。
- 修改歌词文字和起止时间，分别提供 ±50ms、±200ms 微调按钮。
- 时间轴定位同步选中下方原句，支持空格播放/暂停、单句试听、插入、删除、撤销和重做。
- 可调分辨率、帧率、字体、字号、背景、多行排版、滚动、倒计时和视频编码。
- 支持简体中文、English、日本語，首次根据系统语言选择；其他系统语言回退到英文。

## 运行说明

标准包不含模型、字体、CUDA/cuDNN 和 ASIO 扩展。自动识别首次需单独下载模型，下载后可离线使用；CPU 对轴、普通音频播放和默认 x264 视频导出可直接使用。GPU 对轴需要用户另行配置兼容运行库；NVENC 等硬件编码另取决于硬件与驱动支持。

[完整使用手册](https://github.com/ben19910518/TeleprompterMaker/blob/main/docs/USER_GUIDE.md) · [发行与重建说明](https://github.com/ben19910518/TeleprompterMaker/blob/main/docs/DISTRIBUTION.md) · [第三方声明](https://github.com/ben19910518/TeleprompterMaker/blob/main/THIRD_PARTY_NOTICES.md)

## 发行资料修订 2026-10-26-r1

在最初源码发布后补充 Windows 运行附件。应用功能版本仍为 1.3.0，原本地 ZIP 保留；新包加入详细手册、截图、许可证、第三方 NOTICE、来源、完整对应源码与构建资料，剔除了未再分发的 cuDNN/ASIO 扩展和无关架构的音频 DLL。

FFmpeg 上游分类补丁造成的许可报告差异，以及 LAME 仓库改名造成的压缩包哈希差异，均在配套源码和发行说明中记录；LAME 的 82 个源文件已逐个核对指定版本 Git tree。

验证：现有 26 项测试通过；实际 EXE 完成 CPU 模型加载与转录、6 秒 MP4 导出；两个 ZIP 的 CRC 和 SHA-256 校验通过。内部需求和后续功能规划文档未上传。
