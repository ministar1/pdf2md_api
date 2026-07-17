# AGENTS.md

本文件适用于仓库根目录及其所有子目录，用于约束后续自动化代理和维护者的开发行为。若子目录以后增加更具体的 `AGENTS.md`，以离目标文件最近的说明为准。

## 项目定位

本项目是面向 Windows 的 MinerU PDF 批量转 Markdown 工具。用户通常通过 `run.bat` 操作；核心逻辑位于 `scripts/mineru_pdf2md.py`，只使用 Python 标准库，通过 MinerU 批量 API 完成申请上传 URL、上传 PDF、轮询、下载 zip、解压和重命名 Markdown。

维护时优先保证：Windows 双击可用、错误可诊断、单个 PDF 失败不影响其他文件、Token 和本地文档不会进入版本库。

## 仓库结构

- `scripts/mineru_pdf2md.py`：转换主流程、API 请求、输入预检、交互、结果解压和报告生成。
- `scripts/set_token.py`：创建 `.env` 默认配置或仅替换 `MINERU_API_TOKEN`。
- `tests/test_mineru_pdf2md.py`：基于标准库 `unittest` 的离线单元测试。
- `run.bat`：Windows 用户入口；必要时先引导设置 Token。
- `set_token.bat` / `edit_token.bat`：Token 更新和完整配置编辑入口。
- `input/`：本地待处理 PDF，仅扫描第一层；除 `.gitkeep` 外不得提交。
- `output/`：转换产物和 `conversion_report.txt`；除 `.gitkeep` 外不得提交。
- `README.md`：面向使用者的中文说明，应与实际交互和配置保持一致。
- `pyproject.toml` / `uv.lock`：Python 版本和 `uv` 环境元数据；当前没有第三方运行时依赖。

## 环境与常用命令

要求 Python 3.10+ 和 `uv`。使用仓库既有的 `uv` 工作流，不要改用 Poetry、Pipenv 或裸 `pip`。

```powershell
# 同步锁定环境
uv sync --locked

# 运行全部离线测试
uv run python -m unittest discover -s tests -v

# 可选的语法检查
uv run python -m compileall -q scripts tests

# 直接运行主程序；日常 Windows 使用仍以 run.bat 为入口
uv run python scripts/mineru_pdf2md.py
```

测试命令必须能在没有 `.env`、没有真实 PDF、没有网络访问的环境中运行。除非任务明确要求集成验证并获准使用外部服务，否则不要用真实 Token 或真实文档调用 MinerU API。

## 核心流程与行为约束

主流程保持以下顺序：

1. 从项目根目录读取 `.env`，并扫描 `input/*.pdf`。
2. 在发起网络请求前检查扩展名、文件存在性、空文件、PDF 文件头、200 MB 限制和 Windows 路径长度。
3. 收集语言、页码范围、OCR 和已存在输出目录的交互选择。
4. 每批最多提交 50 个任务，并用唯一 `data_id` 将 API 结果映射回输入文件。
5. 每个文件独立记录 `success`、`skipped` 或 `failed`；单文件错误不得终止其余文件。
6. 下载并保留 MinerU 原始 zip，解压资源，将 `full.md` 重命名为 PDF 同名 Markdown。
7. 每次运行覆写 `output/conversion_report.txt`，终端和报告都给出汇总及可定位的失败原因。

修改时保留以下外部行为：

- 只处理 `input` 根目录的 `.pdf`，不要无提示地改为递归扫描。
- 已有输出目录必须先让用户选择跳过、覆盖或取消；只有明确选择覆盖时才可删除该目录。
- 配置错误和转换前检查应尽早失败，不要在已知无效时上传文件。
- API/文件错误使用 `ConversionError` 并填写稳定、具体的 `stage`；报告仍需包含 HTTP 状态、MinerU 错误和异常摘要。
- 进程退出码保持可用于脚本判断：正常完成为 `0`，配置错误、取消或存在失败为非零，中断为 `130`。
- 不在日志、异常、测试夹具或报告中输出 `MINERU_API_TOKEN`。

## 配置同步规则

当前配置项为：

- `MINERU_API_TOKEN`
- `MINERU_LANGUAGE`
- `MINERU_MODEL_VERSION`
- `MINERU_ENABLE_OCR`
- `MINERU_ENABLE_FORMULA`
- `MINERU_ENABLE_TABLE`

新增、删除或修改配置项时，同时检查并按需更新：

1. `scripts/mineru_pdf2md.py` 的读取、默认值和校验；
2. `scripts/set_token.py` 的 `DEFAULT_ENV_LINES`，同时确保替换 Token 时保留其他行；
3. `README.md` 的默认 `.env` 示例、配置说明和运行提示；
4. 对应单元测试；
5. 若用户入口发生变化，再同步相关 `.bat` 文件。

不得提交 `.env`，也不得用示例真实 Token 替换空值。保持当前优先级：优先使用 `.env` 中的值，仅在其中没有对应键时回退读取进程环境变量。

## Python 与批处理约定

- Python 使用 4 空格缩进、类型注解、`pathlib.Path`、数据类和标准库优先；保持兼容 Python 3.10+。
- 当前没有配置格式化器、linter 或测试框架插件，不要在说明中假定它们存在。
- 网络、解析、轮询和文件操作应拆成可独立测试的小函数；避免把新逻辑全部塞入 `main()`。
- 用户可见提示、报告和 README 默认使用中文；API 字段、状态值和原始错误可保留英文。
- 文本文件显式使用 UTF-8。`.bat` 文件保持 `chcp 65001 >nul`，并从 `%~dp0` 切换到项目根目录，保证双击运行与中文提示正常。
- 新增生产依赖前必须先获得用户同意；确有需要时使用 `uv add` 并同时提交 `pyproject.toml` 与 `uv.lock`。

## 测试要求

所有行为变更都应补充或调整测试，优先沿用以下方式：

- 使用 `tempfile.TemporaryDirectory()` 隔离文件系统。
- 使用 `unittest.mock` 模拟 `input()`、网络、时间等待和模块常量。
- 不依赖开发机现有 `.env`、`input/` 或 `output/` 内容。
- 覆盖成功路径和失败路径，特别关注配置校验、页码解析、PDF 预检、批次切分、结果字段兼容、覆盖/跳过/取消和错误报告。
- 网络协议变更至少测试请求载荷、响应字段映射、异常转换及超时行为，测试本身仍应离线。

提交前至少运行：

```powershell
uv run python -m unittest discover -s tests -v
```

如改动 `.bat` 或交互流程，还应在 Windows 中人工检查入口、默认值、退出码和中文显示。真实 MinerU 端到端测试只在任务明确要求时进行，并使用无敏感内容的测试 PDF。

## 文档与版本库卫生

- 用户可见行为、配置默认值、目录结构或运行步骤变化时，同步更新中文 `README.md`。
- 不提交 `.env`、`.venv/`、Python 缓存、输入 PDF、转换结果、报告或 MinerU 返回的 zip/资源。
- 保留 `input/.gitkeep` 和 `output/.gitkeep`，不要为清理生成物而删除占位文件。
- 开始修改前检查 `git status`；工作区已有改动默认属于用户，不覆盖、不回滚、不顺手格式化无关文件。
- 修改尽量聚焦，避免在功能修复中进行大范围无关重构；提交信息沿用仓库现有的简洁英文祈使风格。
