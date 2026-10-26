# Windows 绿色包与第三方源码说明

版本：v1.3.0；打包资料修订：2026-10-26-r1。应用功能版本未改变。

## 普通用户下载

在 [v1.3.0 Release](https://github.com/ben19910518/TeleprompterMaker/releases/tag/v1.3.0) 下载 `TeleprompterMaker_v1.3.0_Windows_x64.zip`，完整解压后双击 EXE。不要单独移动 EXE 或删除 `_internal`。

`TeleprompterMaker_v1.3.0_ThirdPartySources.zip` 是配套源码与重建资料，普通使用无需解压它。需要修改、重新构建或再分发时，请同时保留其提供的对应源码及许可资料。

运行包附带完整使用手册、界面截图、项目 LICENSE、第三方声明、原始许可文本、组件清单、源码来源及二进制校验清单。它不包含模型、字体、CUDA/cuDNN 或 ASIO 扩展。常规音频播放、CPU 对轴和 x264 导出可用；GPU 对轴需用户另行准备兼容运行库，视频硬件编码另受驱动和硬件支持限制。

## 本次打包处理

- 原本地运行包保留，没有覆盖或删除。
- 应用 EXE 与功能代码沿用 v1.3.0；补充文档、许可与出处资料。
- 未再分发 CTranslate2 wheel 附带的 cuDNN DLL、ASIO 版 PortAudio 和无关的其他架构音频 DLL。Windows x64 普通 PortAudio 保留。
- Qt 对话框翻译由仓库中的对应 TS 源文件重新生成。
- 项目采用 GPL-3.0-only；第三方组件保留各自许可。Qt/PySide6 运行库采用其提供的 LGPL-3.0 选项，完整对应源码和重建资料随源码附件提供。允许按这些条款替换库和重新构建，不增加限制修改或调试的条款。

## FFmpeg 报告与实际许可

实际运行库为 FFmpeg 9.0.2，构建来源为 PyAV-Org/pyav-ffmpeg 的 9.0.2-1 配方。该配方的 `patches/ffmpeg.patch` 将 x264/x265 改列为 version3 库，导致运行时报告 LGPL version 3 or later；这不能替代 x264/x265 的 GPL 条款。本次将含这些编解码器的组合按 GPL-3.0 条件分发，提供 GPL 正文以及 FFmpeg、x264/x265、相关依赖和上游补丁/构建脚本的完整源码。

详细配置记录见源码包 `provenance/ffmpeg-runtime.json`。本次未静默更改 DLL 内部的上游报告。

LAME 上游仓库从 lamer 改名为 bwlame，GitHub 自动生成的压缩包前缀和 SHA-256 随之变化。本次未跳过验证：压缩包中的 82 个源文件逐个核对了指定版本 Git tree 的 blob 哈希，证明源内容与 v3.101.0 对应。记录见 `provenance/lamer-source-provenance.json`。

## 源码附件结构

```text
ApplicationSource/         应用源码、翻译、测试和打包脚本
sources/                   上游原始源码压缩包，保留原文件内容
licenses/                  提取保留的版权、许可、NOTICE 与 Qt attribution
provenance/                FFmpeg、LAME 与 Intel OpenMP 来源记录
SOURCE_MANIFEST.json       源码 URL、版本、大小与 SHA-256
BINARY_INVENTORY.json      运行包内 EXE/DLL/PYD 的相对路径与 SHA-256
INSTALLED_COMPONENTS.json  构建环境组件版本与原始许可元数据
```

`licenses/INDEX.json` 将提取文件映射回原始组件、原路径与内容哈希。文件名中的哈希用于避免不同组件同名 LICENSE 相互覆盖。构建环境清单包含部分构建工具，不表示每个列出的工具都打入 EXE。

## 重建应用

在 Windows x64 配置 Python 3.13，使用源码包的 `ApplicationSource`，执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe build_tools\build_i18n_catalog.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm build_tools\TeleprompterMaker.spec
.\.venv\Scripts\python.exe build_tools\package.py
```

这会重建应用，依赖由 requirements 安装。需要修改或重建 Qt/PySide6 等库时，使用 sources 中对应版本的源码与原始 CMake/构建说明：Qt 6.12.0 的 qtbase、qtsvg、qtimageformats、qttranslations；Python 绑定和 shiboken 源码位于 pyside-setup；Qt 的第三方组件源码与许可保留在相应源树中。可替换动态库或从源码重建应用与绑定；请保持 ABI 匹配。

FFmpeg 的完整 Windows 构建脚本、依赖版本/哈希和补丁在 pyav-ffmpeg-9.0.2-1.tar.gz。该源码包包括其配方中用到的 Windows 依赖。若重新制作标准 GPL 构建，应保留适用的编解码器许可，并使配置/报告与实际分发许可一致。PyAV 对应源码为 av-19.0.1.tar.gz。

CTranslate2 的 Windows 构建步骤在其 `python/tools/prepare_build_environment_windows.sh`，引用 CUDA 12.8、Intel oneAPI 2025.3 和 oneDNN 3.1.1。相关开源依赖和子模块的源码附在 sources；需使用厂商 SDK 的构建步骤应由开发者按其条款自行配置，源码附件不分发这些专有 SDK。Intel OpenMP 的原始再分发许可保存在 licenses。

Python 3.13.16 的标准构建脚本和 PCbuild 外部依赖版本随 CPython 源码提供；相关外部库源码也已附上。MSVC 运行库许可、GCC runtime exception 和 MinGW 声明保留在 licenses。

## 重新组合公开运行包

`build_tools/package_public_release.py` 记录本次加入文档/许可、保留源码、生成清单、剔除未分发扩展和 ZIP/SHA-256 的过程。输入来自清单所列源码缓存与已经验证的运行目录；它不会执行下载的第三方源码。

## 验证结果

现有 26 项测试通过。实际打包 EXE 在不使用 CUDA 的情况下完成导入自检、CPU 模型加载/转录和 6 秒 MP4 导出。ZIP CRC、源码哈希和运行包二进制清单另行核对。该自检不代表已经验证所有显卡、音频设备或歌曲识别准确率。
