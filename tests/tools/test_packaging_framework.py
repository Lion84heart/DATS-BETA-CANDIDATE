"""Tests for the Packaging & Release Validation Framework.

Uses standard unittest to avoid external dependencies.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.packaging_framework import PackagingFramework, Status


class TestPackagingFramework(unittest.TestCase):
    """Integration tests for the full packaging pipeline."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sample_project = Path(self.tmp) / "sample_project"
        self.sample_project.mkdir()

        # Create source files
        (self.sample_project / "src").mkdir()
        (self.sample_project / "src" / "main.py").write_text("print('hello')\n")
        (self.sample_project / "src" / "utils.py").write_text("def add(a, b):\n    return a + b\n")

        (self.sample_project / "tests").mkdir()
        (self.sample_project / "tests" / "test_main.py").write_text("def test_add():\n    assert 1 + 1 == 2\n")

        (self.sample_project / "docs").mkdir()
        (self.sample_project / "docs" / "readme.md").write_text("# Sample\n")

        # Cache dir (should be excluded)
        (self.sample_project / "__pycache__").mkdir()
        (self.sample_project / "__pycache__" / "cached.pyc").write_text("cache")

        self.output_dir = Path(self.tmp) / "output"
        self.output_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_pipeline_passes(self):
        """The full pipeline should pass on a valid project."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        report = fw.run()

        failed = [c for c in report.checks if c.status == Status.FAIL]
        self.assertEqual(len(failed), 0, f"Failed checks: {[c.name for c in failed]}")
        self.assertTrue(fw.gate_passed())
        self.assertGreaterEqual(len(report.artifacts), 2)
        self.assertGreaterEqual(report.source_files, 4)
        self.assertGreater(report.source_bytes, 0)
        fw.cleanup()

    def test_exclusions_applied(self):
        """Excluded directories should not be in the archive."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        report = fw.run()

        zip_art = [a for a in report.artifacts if a.format == "zip"]
        self.assertTrue(len(zip_art) > 0, "ZIP artifact not found")

        import zipfile
        with zipfile.ZipFile(zip_art[0].path, "r") as z:
            names = z.namelist()

        self.assertFalse(any("__pycache__" in n for n in names), "__pycache__ included")
        self.assertFalse(any(n.endswith(".pyc") for n in names), ".pyc included")
        fw.cleanup()

    def test_zip_structure_valid(self):
        """ZIP structure validation should pass."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        report = fw.run()

        zip_valid = [c for c in report.checks if c.name == "ZIP Valid"]
        self.assertEqual(len(zip_valid), 1)
        self.assertEqual(zip_valid[0].status, Status.PASS)
        self.assertIn("entries", zip_valid[0].detail.lower())
        fw.cleanup()

    def test_archive_integrity(self):
        """Archive integrity test (CRC) should pass."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        report = fw.run()

        integrity = [c for c in report.checks if c.name == "Archive Integrity"]
        self.assertEqual(len(integrity), 1)
        self.assertEqual(integrity[0].status, Status.PASS)
        self.assertIn("crc", integrity[0].detail.lower())
        fw.cleanup()

    def test_extraction_verification(self):
        """Extraction test should pass."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        report = fw.run()

        extraction = [c for c in report.checks if c.name == "Extraction Test"]
        self.assertEqual(len(extraction), 1)
        self.assertEqual(extraction[0].status, Status.PASS)
        self.assertIn("extracted", extraction[0].detail.lower())
        fw.cleanup()

    def test_checksums_generated(self):
        """All artifacts should have SHA-256 checksums."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        report = fw.run()

        checksums = [c for c in report.checks if c.name == "Checksums Valid"]
        self.assertEqual(len(checksums), 1)
        self.assertEqual(checksums[0].status, Status.PASS)

        for art in report.artifacts:
            self.assertEqual(len(art.sha256), 64, f"Invalid SHA-256 for {art.path}")
        fw.cleanup()

    def test_report_generation(self):
        """Reports should be written to output directory."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        report = fw.run()

        paths = fw.write_reports()
        self.assertEqual(len(paths), 2, "Should generate JSON + Markdown")

        for p in paths:
            self.assertTrue(Path(p).exists(), f"Report missing: {p}")
            self.assertGreater(Path(p).stat().st_size, 0, f"Report empty: {p}")

        with open(paths[0]) as f:
            data = json.load(f)
        self.assertEqual(data["overall_status"], "PASS")

        md = Path(paths[1]).read_text()
        self.assertIn("PACKAGING VERIFIED", md)
        fw.cleanup()

    def test_manifest_consistency(self):
        """Manifest should reference only existing files."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        report = fw.run()

        consistency = [c for c in report.checks if c.name == "Manifest Consistency"]
        self.assertEqual(len(consistency), 1)
        self.assertEqual(consistency[0].status, Status.PASS)
        fw.cleanup()

    def test_split_archives(self):
        """Oversized archives should be split into parts."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        fw.SPLIT_THRESHOLD = 50
        fw.PART_SIZE = 30
        report = fw.run()

        split_check = [c for c in report.checks if c.name == "Split Archives"]
        self.assertEqual(len(split_check), 1)
        self.assertEqual(split_check[0].status, Status.PASS)
        fw.cleanup()

    def test_report_formats(self):
        """Report to_dict and to_markdown should produce valid output."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        report = fw.run()

        d = report.to_dict()
        self.assertIn("overall_status", d)
        self.assertIn("ZIP_VALID", d)
        self.assertIn("RELEASE_STATUS", d)
        self.assertGreaterEqual(len(d["checks"]), 16)

        md = report.to_markdown()
        self.assertIn("# Release Verification Report", md)
        self.assertIn("## Verification Checks", md)
        fw.cleanup()

    def test_cleanup_removes_workspace(self):
        """Cleanup should remove the temporary workspace."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        fw.run()

        workspace = fw._workspace
        self.assertTrue(workspace.exists(), "Workspace should exist before cleanup")
        fw.cleanup()
        self.assertFalse(workspace.exists(), "Workspace should be removed after cleanup")

    def test_empty_project(self):
        """Empty project should still produce valid archives."""
        empty = Path(self.tmp) / "empty"
        empty.mkdir()
        out = Path(self.tmp) / "empty_out"
        out.mkdir()

        fw = PackagingFramework(str(empty), str(out))
        report = fw.run()
        # Empty project creates 0-byte ZIP; some checks may skip but overall should not fail
        failed = [c for c in report.checks if c.status == Status.FAIL]
        self.assertEqual(len(failed), 0, f"Failed checks: {[f'{c.name}: {c.detail}' for c in failed]}")
        fw.cleanup()

    def test_workspace_isolation(self):
        """Workspace should be in a temp directory, not the project."""
        fw = PackagingFramework(str(self.sample_project), str(self.output_dir))
        fw.run()

        workspace = fw._workspace
        self.assertIsNotNone(workspace)
        self.assertFalse(str(workspace).startswith(str(self.sample_project)))
        fw.cleanup()

    def test_large_file_splitting(self):
        """Files larger than threshold should be split."""
        big_project = Path(self.tmp) / "big"
        big_project.mkdir()
        (big_project / "big_data.bin").write_bytes(b"X" * 500)

        out = Path(self.tmp) / "big_out"
        out.mkdir()

        fw = PackagingFramework(str(big_project), str(out))
        fw.SPLIT_THRESHOLD = 200
        fw.PART_SIZE = 100
        report = fw.run()

        parts = [a for a in report.artifacts if "-part" in a.format]
        self.assertGreater(len(parts), 0, "Large archive should be split")

        total = sum(p.size for p in parts)
        self.assertGreater(total, 0)
        fw.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
