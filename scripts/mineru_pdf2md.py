from __future__ import annotations

import json
import http.client
import os
import shutil
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "input"
OUTPUT_DIR = PROJECT_ROOT / "output"
REPORT_PATH = OUTPUT_DIR / "conversion_report.txt"

MINERU_BATCH_URL = "https://mineru.net/api/v4/file-urls/batch"
MINERU_RESULT_URL_TEMPLATE = "https://mineru.net/api/v4/extract-results/batch/{batch_id}"
MAX_BATCH_SIZE = 50
POLL_INTERVAL_SECONDS = 10
POLL_TIMEOUT_SECONDS = 60 * 60


class ConversionError(Exception):
    def __init__(
        self,
        stage: str,
        message: str,
        *,
        http_status: int | None = None,
        mineru_error: str | None = None,
        original: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.http_status = http_status
        self.mineru_error = mineru_error
        self.original = original


@dataclass
class PdfJob:
    pdf_path: Path
    output_dir: Path
    data_id: str
    overwrite: bool = False

    @property
    def markdown_path(self) -> Path:
        return self.output_dir / f"{self.pdf_path.stem}.md"

    @property
    def zip_path(self) -> Path:
        return self.output_dir / f"{self.pdf_path.stem}_mineru_result.zip"


@dataclass
class ReportEntry:
    file_name: str
    status: str
    output_path: str = ""
    stage: str = ""
    http_status: str = ""
    mineru_error: str = ""
    exception_summary: str = ""
    batch_id: str = ""
    data_id: str = ""
    started_at: str = ""
    finished_at: str = ""


@dataclass
class RunReport:
    started_at: datetime
    input_files: list[Path]
    entries: list[ReportEntry] = field(default_factory=list)
    config_error: str = ""

    def write(self) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        lines.append("MinerU PDF 转 Markdown 转换报告")
        lines.append("=" * 44)
        lines.append(f"运行开始: {self.started_at.isoformat(timespec='seconds')}")
        lines.append(f"运行结束: {datetime.now().isoformat(timespec='seconds')}")
        lines.append(f"项目目录: {PROJECT_ROOT}")
        lines.append(f"输入目录: {INPUT_DIR}")
        lines.append(f"输出目录: {OUTPUT_DIR}")
        lines.append("")
        lines.append("输入文件:")
        if self.input_files:
            for pdf in self.input_files:
                lines.append(f"- {pdf.name}")
        else:
            lines.append("- input 目录下没有 PDF 文件。")
        lines.append("")

        if self.config_error:
            lines.append("配置错误:")
            lines.append(self.config_error)
            lines.append("")

        lines.append("转换结果:")
        if not self.entries:
            lines.append("- 本次没有执行转换任务。")
        else:
            for entry in self.entries:
                lines.append(f"- 文件: {entry.file_name}")
                lines.append(f"  状态: {entry.status}")
                if entry.output_path:
                    lines.append(f"  输出: {entry.output_path}")
                if entry.batch_id:
                    lines.append(f"  Batch ID: {entry.batch_id}")
                if entry.data_id:
                    lines.append(f"  Data ID: {entry.data_id}")
                if entry.stage:
                    lines.append(f"  失败阶段: {entry.stage}")
                if entry.http_status:
                    lines.append(f"  HTTP status: {entry.http_status}")
                if entry.mineru_error:
                    lines.append(f"  MinerU error: {entry.mineru_error}")
                if entry.exception_summary:
                    lines.append(f"  异常摘要: {entry.exception_summary}")
                if entry.started_at:
                    lines.append(f"  开始时间: {entry.started_at}")
                if entry.finished_at:
                    lines.append(f"  结束时间: {entry.finished_at}")
                lines.append("")

        summary = summarize_entries(self.entries)
        lines.append("汇总:")
        lines.append(f"- 成功: {summary['success']}")
        lines.append(f"- 跳过: {summary['skipped']}")
        lines.append(f"- 失败: {summary['failed']}")

        REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize_entries(entries: list[ReportEntry]) -> dict[str, int]:
    summary = {"success": 0, "skipped": 0, "failed": 0}
    for entry in entries:
        if entry.status in summary:
            summary[entry.status] += 1
    return summary


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def env_bool(values: dict[str, str], key: str, default: bool) -> bool:
    value = values.get(key, os.environ.get(key))
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_value(values: dict[str, str], key: str, default: str = "") -> str:
    return values.get(key, os.environ.get(key, default)).strip()


def prompt_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def prompt_bool(prompt: str, default: bool) -> bool:
    suffix = " [y]" if default else " [n]"
    true_values = {"1", "true", "yes", "y", "on"}
    false_values = {"0", "false", "no", "n", "off"}

    while True:
        value = input(f"{prompt}{suffix}: ").strip().lower()
        if not value:
            return default
        if value in true_values:
            return True
        if value in false_values:
            return False
        print("请输入 y 或 n（也可输入 true/false、1/0、on/off）。")


def prompt_existing_output(job: PdfJob) -> str:
    while True:
        choice = input(
            f"'{job.pdf_path.name}' 已存在输出目录。"
            "请选择 [s]跳过、[o]覆盖重跑、[c]取消（默认: s）: "
        ).strip().lower()
        if choice == "":
            choice = "s"
        if choice in {"s", "skip"}:
            return "skip"
        if choice in {"o", "overwrite"}:
            return "overwrite"
        if choice in {"c", "cancel"}:
            return "cancel"
        print("请输入 s、o 或 c。")


def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 60,
    stage: str,
) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        raise ConversionError(
            stage,
            decode_error_body(raw) or str(exc),
            http_status=exc.code,
            mineru_error=decode_error_body(raw),
            original=exc,
        ) from exc
    except urllib.error.URLError as exc:
        raise ConversionError(stage, str(exc.reason), original=exc) from exc
    except OSError as exc:
        raise ConversionError(stage, str(exc), original=exc) from exc


def http_put_presigned_file(url: str, data: bytes, *, stage: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConversionError(stage, "Invalid upload URL returned by MinerU.")

    path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    connection_class = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_class(parsed.netloc, timeout=300)
    try:
        connection.putrequest("PUT", path, skip_host=False, skip_accept_encoding=True)
        connection.putheader("Content-Length", str(len(data)))
        connection.endheaders(data)
        response = connection.getresponse()
        raw = response.read()
        if response.status < 200 or response.status >= 300:
            raise ConversionError(
                stage,
                decode_error_body(raw) or f"Unexpected HTTP status {response.status}.",
                http_status=response.status,
                mineru_error=decode_error_body(raw),
            )
    except OSError as exc:
        raise ConversionError(stage, str(exc), original=exc) from exc
    finally:
        connection.close()


def decode_error_body(raw: bytes) -> str:
    if not raw:
        return ""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    return extract_mineru_error(payload) or text


def extract_mineru_error(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""

    messages: list[str] = []
    for key in ("msg", "message", "err_msg", "error", "detail"):
        value = payload.get(key)
        if value:
            messages.append(str(value))

    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("msg", "message", "err_msg", "error", "detail"):
            value = data.get(key)
            if value:
                messages.append(str(value))

    return "; ".join(dict.fromkeys(messages))


def request_json(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None,
    *,
    stage: str,
    timeout: int = 60,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    status, raw, _ = http_request(method, url, headers=headers, body=body, timeout=timeout, stage=stage)
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ConversionError(stage, "MinerU returned non-JSON response.", http_status=status, original=exc) from exc

    code = decoded.get("code")
    if code not in (0, "0", None):
        raise ConversionError(
            stage,
            extract_mineru_error(decoded) or f"MinerU returned code {code}.",
            http_status=status,
            mineru_error=extract_mineru_error(decoded),
        )
    return decoded


def create_batch(
    token: str,
    jobs: list[PdfJob],
    *,
    language: str,
    model_version: str,
    enable_ocr: bool,
    enable_formula: bool,
    enable_table: bool,
    page_ranges: str,
) -> tuple[str, list[str]]:
    files: list[dict[str, Any]] = []
    for job in jobs:
        item: dict[str, Any] = {
            "name": job.pdf_path.name,
            "is_ocr": enable_ocr,
            "data_id": job.data_id,
        }
        if page_ranges:
            item["page_ranges"] = page_ranges
        files.append(item)

    payload = {
        "enable_formula": enable_formula,
        "enable_table": enable_table,
        "language": language,
        "model_version": model_version,
        "files": files,
    }
    response = request_json("POST", MINERU_BATCH_URL, token, payload, stage="申请上传 URL")
    data = response.get("data")
    if not isinstance(data, dict):
        raise ConversionError("申请上传 URL", "MinerU response did not contain data object.")

    batch_id = str(data.get("batch_id") or "")
    raw_urls = data.get("file_urls")
    if not batch_id:
        raise ConversionError("申请上传 URL", "MinerU response did not contain batch_id.")
    if not isinstance(raw_urls, list) or len(raw_urls) != len(jobs):
        raise ConversionError("申请上传 URL", "MinerU response file_urls count did not match submitted files.")

    upload_urls: list[str] = []
    for index, item in enumerate(raw_urls):
        if isinstance(item, str):
            upload_urls.append(item)
            continue
        if isinstance(item, dict):
            url = item.get("url") or item.get("upload_url") or item.get("file_url")
            if url:
                upload_urls.append(str(url))
                continue
        raise ConversionError("申请上传 URL", f"MinerU did not return a usable upload URL for file #{index + 1}.")

    return batch_id, upload_urls


def upload_pdf(job: PdfJob, upload_url: str) -> None:
    try:
        data = job.pdf_path.read_bytes()
    except OSError as exc:
        raise ConversionError("读取文件", str(exc), original=exc) from exc

    http_put_presigned_file(upload_url, data, stage="上传 PDF")


def fetch_batch_results(token: str, batch_id: str) -> list[dict[str, Any]]:
    url = MINERU_RESULT_URL_TEMPLATE.format(batch_id=urllib.parse.quote(batch_id, safe=""))
    response = request_json("GET", url, token, None, stage="轮询结果")
    data = response.get("data")
    if isinstance(data, dict):
        for key in ("extract_result", "extract_results", "results", "files"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def result_key(result: dict[str, Any]) -> str:
    for key in ("data_id", "name", "file_name", "filename"):
        value = result.get(key)
        if value:
            return str(value)
    return ""


def result_state(result: dict[str, Any]) -> str:
    for key in ("state", "status", "extract_status"):
        value = result.get(key)
        if value:
            return str(value).strip().lower()
    return ""


def result_error(result: dict[str, Any]) -> str:
    for key in ("err_msg", "error", "message", "msg", "detail"):
        value = result.get(key)
        if value:
            return str(value)
    return ""


def result_zip_url(result: dict[str, Any]) -> str:
    for key in ("full_zip_url", "zip_url", "result_zip_url"):
        value = result.get(key)
        if value:
            return str(value)
    return ""


def poll_until_done(token: str, batch_id: str, jobs: list[PdfJob]) -> dict[str, dict[str, Any]]:
    pending = {job.data_id for job in jobs}
    terminal: dict[str, dict[str, Any]] = {}
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS

    while pending and time.monotonic() < deadline:
        results = fetch_batch_results(token, batch_id)
        by_key = {result_key(result): result for result in results if result_key(result)}
        by_name = {str(result.get("name") or result.get("file_name") or result.get("filename")): result for result in results}

        for job in jobs:
            if job.data_id not in pending:
                continue
            result = by_key.get(job.data_id) or by_name.get(job.pdf_path.name)
            if not result:
                continue

            state = result_state(result)
            has_zip = bool(result_zip_url(result))
            has_error = bool(result_error(result))

            if has_zip or state in {"done", "success", "completed", "finish", "finished"}:
                terminal[job.data_id] = result
                pending.remove(job.data_id)
            elif has_error or state in {"failed", "fail", "error"}:
                terminal[job.data_id] = result
                pending.remove(job.data_id)

        if pending:
            print(f"等待 MinerU 返回结果... 剩余: {len(pending)}")
            time.sleep(POLL_INTERVAL_SECONDS)

    if pending:
        for job in jobs:
            if job.data_id in pending:
                terminal[job.data_id] = {
                    "data_id": job.data_id,
                    "state": "timeout",
                    "err_msg": f"Timed out after {POLL_TIMEOUT_SECONDS} seconds while waiting for MinerU result.",
                }

    return terminal


def download_and_extract(job: PdfJob, zip_url: str) -> None:
    status, raw, _ = http_request("GET", zip_url, timeout=300, stage="下载 zip")
    if status < 200 or status >= 300:
        raise ConversionError("下载 zip", f"Unexpected HTTP status {status}.", http_status=status)

    if job.overwrite and job.output_dir.exists():
        shutil.rmtree(job.output_dir)
    job.output_dir.mkdir(parents=True, exist_ok=True)
    job.zip_path.write_bytes(raw)

    try:
        with zipfile.ZipFile(job.zip_path) as archive:
            archive.extractall(job.output_dir)
    except zipfile.BadZipFile as exc:
        raise ConversionError("解压结果", "Downloaded result is not a valid zip file.", original=exc) from exc
    except OSError as exc:
        raise ConversionError("解压结果", str(exc), original=exc) from exc

    rename_markdown(job)


def rename_markdown(job: PdfJob) -> None:
    root_full_md = job.output_dir / "full.md"
    candidates = [root_full_md] if root_full_md.exists() else list(job.output_dir.rglob("full.md"))
    if not candidates:
        raise ConversionError("生成 Markdown", "MinerU result zip did not contain full.md.")

    source = candidates[0]
    target = job.markdown_path
    if source.resolve() == target.resolve():
        return
    if target.exists():
        target.unlink()
    shutil.move(str(source), str(target))


def make_failure_entry(job: PdfJob, error: ConversionError, *, batch_id: str = "") -> ReportEntry:
    return ReportEntry(
        file_name=job.pdf_path.name,
        status="failed",
        output_path=str(job.output_dir),
        stage=error.stage,
        http_status=str(error.http_status or ""),
        mineru_error=error.mineru_error or "",
        exception_summary=error.message,
        batch_id=batch_id,
        data_id=job.data_id,
        finished_at=datetime.now().isoformat(timespec="seconds"),
    )


def make_success_entry(job: PdfJob, *, batch_id: str) -> ReportEntry:
    return ReportEntry(
        file_name=job.pdf_path.name,
        status="success",
        output_path=str(job.markdown_path),
        batch_id=batch_id,
        data_id=job.data_id,
        finished_at=datetime.now().isoformat(timespec="seconds"),
    )


def make_skipped_entry(job: PdfJob, reason: str) -> ReportEntry:
    return ReportEntry(
        file_name=job.pdf_path.name,
        status="skipped",
        output_path=str(job.output_dir),
        exception_summary=reason,
        data_id=job.data_id,
        finished_at=datetime.now().isoformat(timespec="seconds"),
    )


def chunked(items: list[PdfJob], size: int) -> list[list[PdfJob]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def prepare_jobs(pdf_files: list[Path]) -> tuple[list[PdfJob], list[ReportEntry], bool]:
    jobs: list[PdfJob] = []
    entries: list[ReportEntry] = []
    cancelled = False

    for pdf in pdf_files:
        job = PdfJob(
            pdf_path=pdf,
            output_dir=OUTPUT_DIR / pdf.stem,
            data_id=uuid.uuid4().hex,
        )

        if job.output_dir.exists():
            choice = prompt_existing_output(job)
            if choice == "skip":
                entries.append(make_skipped_entry(job, "Output already exists; user chose skip."))
                continue
            if choice == "cancel":
                cancelled = True
                entries.append(make_skipped_entry(job, "Run cancelled by user before processing this file."))
                break
            job.overwrite = True

        jobs.append(job)

    return jobs, entries, cancelled


def run_batch(
    token: str,
    jobs: list[PdfJob],
    *,
    language: str,
    model_version: str,
    enable_ocr: bool,
    enable_formula: bool,
    enable_table: bool,
    page_ranges: str,
) -> list[ReportEntry]:
    entries: list[ReportEntry] = []

    try:
        batch_id, upload_urls = create_batch(
            token,
            jobs,
            language=language,
            model_version=model_version,
            enable_ocr=enable_ocr,
            enable_formula=enable_formula,
            enable_table=enable_table,
            page_ranges=page_ranges,
        )
    except ConversionError as error:
        return [make_failure_entry(job, error) for job in jobs]

    uploadable_jobs: list[PdfJob] = []
    for job, upload_url in zip(jobs, upload_urls):
        try:
            upload_pdf(job, upload_url)
            uploadable_jobs.append(job)
            print(f"已上传: {job.pdf_path.name}")
        except ConversionError as error:
            entries.append(make_failure_entry(job, error, batch_id=batch_id))

    if not uploadable_jobs:
        return entries

    try:
        results = poll_until_done(token, batch_id, uploadable_jobs)
    except ConversionError as error:
        entries.extend(make_failure_entry(job, error, batch_id=batch_id) for job in uploadable_jobs)
        return entries

    for job in uploadable_jobs:
        result = results.get(job.data_id, {})
        zip_url = result_zip_url(result)
        mineru_error = result_error(result)
        state = result_state(result)

        if not zip_url:
            error = ConversionError(
                "轮询结果",
                mineru_error or f"MinerU did not return full_zip_url. state={state or 'unknown'}",
                mineru_error=mineru_error,
            )
            entries.append(make_failure_entry(job, error, batch_id=batch_id))
            continue

        try:
            download_and_extract(job, zip_url)
            entries.append(make_success_entry(job, batch_id=batch_id))
            print(f"已转换: {job.pdf_path.name} -> {job.markdown_path}")
        except ConversionError as error:
            entries.append(make_failure_entry(job, error, batch_id=batch_id))

    return entries


def print_summary(entries: list[ReportEntry]) -> None:
    summary = summarize_entries(entries)
    print("")
    print("转换汇总")
    print("------------------")
    print(f"成功: {summary['success']}")
    print(f"跳过: {summary['skipped']}")
    print(f"失败: {summary['failed']}")
    print(f"报告: {REPORT_PATH}")

    failures = [entry for entry in entries if entry.status == "failed"]
    if failures:
        print("")
        print("失败文件:")
        for entry in failures:
            details = entry.exception_summary or entry.mineru_error or "Unknown error"
            print(f"- {entry.file_name}: {entry.stage or 'unknown stage'} - {details}")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    env = load_env(PROJECT_ROOT / ".env")
    pdf_files = sorted(INPUT_DIR.glob("*.pdf"), key=lambda path: path.name.lower())
    report = RunReport(started_at=datetime.now(), input_files=pdf_files)

    token = env_value(env, "MINERU_API_TOKEN")
    if not token:
        report.config_error = "缺少 MINERU_API_TOKEN。请运行 set_token.bat 粘贴或替换 MinerU token。"
        report.write()
        print(report.config_error)
        print(f"报告: {REPORT_PATH}")
        return 1

    if not pdf_files:
        report.write()
        print(f"{INPUT_DIR} 下没有找到 PDF 文件。")
        print(f"报告: {REPORT_PATH}")
        return 0

    default_language = env_value(env, "MINERU_LANGUAGE", "en") or "en"
    language = prompt_text("MinerU 语言参数（常用备选项：ch、en、japan、korean），回车保留默认值", default_language)
    page_ranges = prompt_text("所有 PDF 的页码范围，例如 1-3 或 1,3-5，回车表示全部页", "")
    default_enable_ocr = env_bool(env, "MINERU_ENABLE_OCR", True)
    enable_ocr = prompt_bool(
        "是否启用 OCR（常见可复制文字的学术论文可关闭；扫描件/图片 PDF 建议开启；输入 y/yes 开启，输入 n/no 关闭），回车保留默认值",
        default_enable_ocr,
    )

    model_version = env_value(env, "MINERU_MODEL_VERSION", "vlm") or "vlm"
    enable_formula = env_bool(env, "MINERU_ENABLE_FORMULA", True)
    enable_table = env_bool(env, "MINERU_ENABLE_TABLE", True)

    print("")
    print(f"找到 {len(pdf_files)} 个 PDF 文件。")
    jobs, initial_entries, cancelled = prepare_jobs(pdf_files)
    report.entries.extend(initial_entries)

    if cancelled:
        report.write()
        print("用户取消了本次运行。")
        print_summary(report.entries)
        return 1

    if not jobs:
        report.write()
        print("没有选择需要转换的 PDF 文件。")
        print_summary(report.entries)
        return 0

    for batch in chunked(jobs, MAX_BATCH_SIZE):
        report.entries.extend(
            run_batch(
                token,
                batch,
                language=language,
                model_version=model_version,
                enable_ocr=enable_ocr,
                enable_formula=enable_formula,
                enable_table=enable_table,
                page_ranges=page_ranges,
            )
        )
        report.write()

    report.write()
    print_summary(report.entries)
    return 1 if any(entry.status == "failed" for entry in report.entries) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        raise SystemExit(130)
    except Exception as exc:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            "MinerU PDF 转 Markdown 转换报告\n"
            "============================================\n"
            f"未预期的致命错误: {exc}\n\n"
            f"{traceback.format_exc()}\n",
            encoding="utf-8",
        )
        print(f"未预期的致命错误: {exc}")
        print(f"报告: {REPORT_PATH}")
        raise SystemExit(1)
