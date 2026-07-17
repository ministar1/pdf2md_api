# MinerU PDF 转 Markdown 一键工具

这是一个面向 Windows 的 MinerU API 批量转换工具，用于把 `input` 文件夹中的 PDF 转换为 Markdown，并把结果保存到 `output` 文件夹。项目提供一键运行的 `.bat` 脚本，也提供 token 快速更换脚本，适合 MinerU token 过期后反复替换使用。

当前实现使用 MinerU 官方批量接口：先申请上传 URL，再上传 PDF，随后轮询解析结果，最后下载 MinerU 返回的 zip 并解压为本地 Markdown 和资源文件。

## 目录结构

```text
pdf2md/
├─ input/                 # 放入待转换 PDF，只处理第一层 .pdf 文件
├─ output/                # 转换结果和 conversion_report.txt
├─ scripts/
│  ├─ mineru_pdf2md.py    # 主转换脚本
│  └─ set_token.py        # 创建或更新 .env 中的 MinerU token
├─ run.bat                # 一键转换入口
├─ set_token.bat          # 快速替换 MinerU token
├─ edit_token.bat         # 手动编辑完整 .env 配置
├─ .gitignore             # 排除 token、输入 PDF、输出结果
└─ README.md
```

`input/.gitkeep` 和 `output/.gitkeep` 只是为了让空目录能被 Git 保留，没有业务含义。

## 环境要求

- Windows
- 已安装 `uv`
- 可访问 MinerU API
- 有有效的 MinerU API token

本项目不要求系统 PATH 中存在 `python`。`run.bat` 会通过 `uv run python ...` 启动脚本。

## 配置 MinerU Token

token 保存在本地 `.env` 文件中。`.env` 已被 `.gitignore` 排除，不应上传到 GitHub。

首次使用或 token 过期后，双击：

```text
set_token.bat
```

然后在终端提示处粘贴新的 token：

```text
MINERU_API_TOKEN: 粘贴你的新 token
```

脚本会只替换 `.env` 中的 `MINERU_API_TOKEN`，并保留其他配置项。这样 token 过期后无需手动找配置文件，只需要重新运行 `set_token.bat`。

如果你想手动编辑完整配置，可以双击：

```text
edit_token.bat
```

它会用记事本打开 `.env`。

## .env 配置项

`.env` 由 `set_token.bat` 或 `edit_token.bat` 自动创建，默认内容如下：

```env
MINERU_API_TOKEN=
MINERU_LANGUAGE=en
MINERU_MODEL_VERSION=vlm
MINERU_ENABLE_OCR=true
MINERU_ENABLE_FORMULA=true
MINERU_ENABLE_TABLE=true
```

配置说明：

- `MINERU_API_TOKEN`：MinerU API token。
- `MINERU_LANGUAGE`：默认语言参数，当前默认 `en`。
- `MINERU_MODEL_VERSION`：默认 `vlm`。
- `MINERU_ENABLE_OCR`：是否开启 OCR，默认 `true`。扫描版论文、拍照 PDF 或图片型 PDF 建议开启；常见可复制文字的学术论文可改为 `false`，或运行时临时关闭。
- `MINERU_ENABLE_FORMULA`：是否开启公式识别，默认 `true`。
- `MINERU_ENABLE_TABLE`：是否开启表格识别，默认 `true`。

## 更换语言

语言有两种调整方式。

长期默认值：编辑 `.env` 中的 `MINERU_LANGUAGE`：

```env
MINERU_LANGUAGE=en
```

运行时临时值：双击 `run.bat` 后，终端会提示：

```text
MinerU 语言参数（常用备选项：ch、en、japan、korean），回车保留默认值 [en]:
```

直接回车使用 `.env` 默认值；输入常用备选项如 `ch`、`en`、`japan`、`korean`，或其他 MinerU 支持的语言值，则仅对本次运行生效。

## 调整 OCR

OCR 默认开启，适合扫描版论文、拍照 PDF 或图片型 PDF。常见可复制文字的学术论文如果不需要 OCR，可以长期修改 `.env`：

```env
MINERU_ENABLE_OCR=false
```

也可以在双击 `run.bat` 后，按终端提示仅对本次运行临时开启或关闭。

## 输入规则

把 PDF 文件放入：

```text
input/
```

当前只处理 `input` 第一层的 `.pdf` 文件，不递归处理子目录。

示例：

```text
input/
├─ paper-a.pdf
└─ paper-b.pdf
```

程序会在上传前检查空文件、PDF 文件头、200MB 大小限制和 Windows 路径长度；
路径过长时会在报告中提示缩短 PDF 文件名或项目路径。

## 一键运行

双击：

```text
run.bat
```

运行过程会提示：

- MinerU 语言参数：提示会显示常用备选项 `ch`、`en`、`japan`、`korean`；回车使用 `.env` 默认值，输入某个语言值则仅对本次运行生效。
- 页码范围：回车表示全部页；也可以输入 `1-3` 或 `1,3-5`。
- 是否启用 OCR：提示会显示当前默认值，例如 `[y]` 表示默认开启；回车使用 `.env` 默认值，输入 `y` 或 `yes` 表示开启，输入 `n` 或 `no` 表示关闭，且仅对本次运行生效。
- 如果输出目录已存在：可选择跳过、覆盖重跑或取消。

示例提示：

```text
MinerU 语言参数（常用备选项：ch、en、japan、korean），回车保留默认值 [en]:
是否启用 OCR（常见可复制文字的学术论文可关闭；扫描件/图片 PDF 建议开启；输入 y/yes 开启，输入 n/no 关闭），回车保留默认值 [y]:
```

如果 `.env` 不存在，`run.bat` 会先提示你粘贴 MinerU token，并自动创建 `.env`。

## 输出结构

每个 PDF 会输出到 `output` 下的同名目录。

示例输入：

```text
input/paper-a.pdf
```

对应输出：

```text
output/paper-a/
├─ paper-a.md
├─ paper-a_mineru_result.zip
├─ images/
├─ layout.json
└─ 其他 MinerU 返回的资源文件
```

说明：

- Markdown 文件由 MinerU zip 中的 `full.md` 改名为 PDF 同名 `.md`。
- 图片、布局 JSON、模型 JSON、原始 PDF 等资源按 MinerU zip 原结构保留。
- MinerU 原始结果 zip 会保留，方便后续排查或重新解压。

## 错误报告

每次运行都会覆写：

```text
output/conversion_report.txt
```

报告不会追加旧内容，因此它始终表示最近一次运行结果。

报告会记录：

- 运行开始和结束时间
- 输入文件列表
- 每个 PDF 的状态：`success`、`skipped` 或 `failed`
- 输出路径
- MinerU `Batch ID` 和内部 `Data ID`
- 失败阶段
- HTTP 状态码
- MinerU 返回的错误信息
- 异常摘要

失败阶段会尽量细分为：

- 读取文件
- 申请上传 URL
- 上传 PDF
- 轮询结果
- 下载 zip
- 解压结果
- 生成 Markdown

终端窗口也会显示本次成功、跳过、失败数量，并列出失败文件的主要原因。

## 已实现行为

- 一键 `.bat` 转换。
- `.env` 本地保存 token。
- `set_token.bat` 快速替换过期 token。
- `edit_token.bat` 手动编辑完整配置。
- 只扫描 `input` 根目录 PDF。
- 每个 PDF 一个同名输出目录。
- Markdown 改名为 PDF 同名 `.md`。
- 保留 MinerU zip 和解压资源。
- 已有输出目录时交互确认跳过、覆盖或取消。
- 单个 PDF 失败不影响其他 PDF 继续处理。
- 终端和报告文件同时显示错误信息。
- 报告文件每次运行覆写。

## GitHub 上传注意事项

项目默认不会上传以下本地数据：

- `.env`
- `input` 中的 PDF
- `output` 中的转换结果
- Python 缓存文件

这些规则写在 `.gitignore` 中。上传到 GitHub 前，请不要手动把 `.env`、PDF 原文或转换结果强行加入 Git。
