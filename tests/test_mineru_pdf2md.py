from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import mineru_pdf2md as mineru


class PageRangeTests(unittest.TestCase):
    def test_normalizes_supported_page_ranges(self) -> None:
        cases = {
            "": "",
            "1-3": "1-3",
            "1,3-5": "1,3-5",
            "2--2": "2--2",
            " 1, 3-5 ": "1,3-5",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(mineru.normalize_page_ranges(raw), expected)

    def test_rejects_invalid_page_ranges(self) -> None:
        for raw in ("0", "1-", "3-1", "1,,2", "abc"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    mineru.normalize_page_ranges(raw)


class ConfigValidationTests(unittest.TestCase):
    def test_rejects_invalid_boolean_and_model(self) -> None:
        errors = mineru.validate_env_config(
            {
                "MINERU_ENABLE_OCR": "ture",
                "MINERU_ENABLE_FORMULA": "true",
                "MINERU_ENABLE_TABLE": "false",
                "MINERU_MODEL_VERSION": "MinerU-HTML",
            }
        )
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("MINERU_ENABLE_OCR" in error for error in errors))
        self.assertTrue(any("MINERU_MODEL_VERSION" in error for error in errors))

    def test_accepts_supported_values(self) -> None:
        self.assertEqual(
            mineru.validate_env_config(
                {
                    "MINERU_ENABLE_OCR": "false",
                    "MINERU_ENABLE_FORMULA": "yes",
                    "MINERU_ENABLE_TABLE": "1",
                    "MINERU_MODEL_VERSION": "vlm",
                }
            ),
            [],
        )


class PdfPreflightTests(unittest.TestCase):
    def test_accepts_valid_pdf_and_rejects_bad_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "output"

            valid_pdf = root / "paper.pdf"
            valid_pdf.write_bytes(b"%PDF-1.7\nvalid")
            mineru.validate_pdf_job(
                mineru.create_pdf_job(valid_pdf, output_root=output_root),
                platform_name="posix",
            )

            empty_pdf = root / "empty.pdf"
            empty_pdf.write_bytes(b"")
            with self.assertRaises(mineru.ConversionError):
                mineru.validate_pdf_job(
                    mineru.create_pdf_job(empty_pdf, output_root=output_root),
                    platform_name="posix",
                )

            wrong_extension = root / "paper.txt"
            wrong_extension.write_bytes(b"%PDF-1.7\n")
            with self.assertRaises(mineru.ConversionError):
                mineru.validate_pdf_job(
                    mineru.create_pdf_job(wrong_extension, output_root=output_root),
                    platform_name="posix",
                )

            bad_header = root / "broken.pdf"
            bad_header.write_bytes(b"not a pdf")
            with self.assertRaises(mineru.ConversionError):
                mineru.validate_pdf_job(
                    mineru.create_pdf_job(bad_header, output_root=output_root),
                    platform_name="posix",
                )

    def test_rejects_oversized_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf_path = root / "large.pdf"
            pdf_path.write_bytes(b"%PDF-1.7\n12345")
            job = mineru.create_pdf_job(pdf_path, output_root=root / "output")
            with mock.patch.object(mineru, "MAX_PDF_SIZE_BYTES", 8):
                with self.assertRaises(mineru.ConversionError):
                    mineru.validate_pdf_job(job, platform_name="posix")

    def test_rejects_long_windows_output_path(self) -> None:
        long_name = "a" * 150 + ".pdf"
        job = mineru.create_pdf_job(
            Path("C:/input") / long_name,
            output_root=Path("C:/output"),
        )
        with self.assertRaises(mineru.ConversionError):
            mineru.validate_path_lengths(job, platform_name="nt")


class ResultMappingTests(unittest.TestCase):
    def test_maps_result_fields(self) -> None:
        result = {
            "data_id": "job-1",
            "state": "DONE",
            "full_zip_url": "https://example.test/result.zip",
            "err_msg": "",
        }
        self.assertEqual(mineru.result_key(result), "job-1")
        self.assertEqual(mineru.result_state(result), "done")
        self.assertEqual(mineru.result_zip_url(result), "https://example.test/result.zip")
        self.assertEqual(mineru.result_error(result), "")


class JobPreparationTests(unittest.TestCase):
    def test_existing_output_can_be_skipped_without_queuing_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "output"
            output_root.mkdir()
            pdf_path = root / "paper.pdf"
            (output_root / "paper").mkdir()

            with (
                mock.patch.object(mineru, "OUTPUT_DIR", output_root),
                mock.patch.object(mineru, "prompt_existing_output", return_value="skip"),
            ):
                jobs, entries, cancelled = mineru.prepare_jobs([pdf_path])

            self.assertFalse(cancelled)
            self.assertEqual(jobs, [])
            self.assertEqual([entry.status for entry in entries], ["skipped"])
            self.assertTrue(entries[0].started_at)

    def test_cancel_records_every_unprocessed_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "output"
            output_root.mkdir()
            pdf_files = [root / "a.pdf", root / "b.pdf", root / "c.pdf"]
            (output_root / "b").mkdir()

            with (
                mock.patch.object(mineru, "OUTPUT_DIR", output_root),
                mock.patch.object(mineru, "prompt_existing_output", return_value="cancel"),
            ):
                jobs, entries, cancelled = mineru.prepare_jobs(pdf_files)

            self.assertTrue(cancelled)
            self.assertEqual(jobs, [])
            self.assertEqual({entry.file_name for entry in entries}, {"a.pdf", "b.pdf", "c.pdf"})
            self.assertTrue(all(entry.status == "skipped" for entry in entries))
            self.assertTrue(all(entry.started_at for entry in entries))


class BatchChunkTests(unittest.TestCase):
    def test_chunks_jobs_without_dropping_items(self) -> None:
        jobs = [mineru.create_pdf_job(Path(f"paper-{index}.pdf")) for index in range(5)]
        batches = mineru.chunked(jobs, 2)
        self.assertEqual([len(batch) for batch in batches], [2, 2, 1])
        self.assertEqual([job for batch in batches for job in batch], jobs)


if __name__ == "__main__":
    unittest.main()
