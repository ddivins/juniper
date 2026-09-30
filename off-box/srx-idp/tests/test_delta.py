import tempfile
import unittest
from pathlib import Path

import openpyxl

from srx_idp.delta import build_junos_commands, create_delta_report, retired_section, select_delta_rows


class DeltaTests(unittest.TestCase):
    def test_selects_and_sorts_newer_signatures(self):
        rows = [
            {"signature_update_number": 12, "signature_name": "B"},
            {"signature_update_number": 10, "signature_name": "OLD"},
            {"signature_update_number": 11, "signature_name": "A"},
        ]
        selected = select_delta_rows(rows, 10)
        self.assertEqual([11, 12], [row["signature_update_number"] for row in selected])

    def test_commands_are_deduplicated_and_sorted(self):
        commands = build_junos_commands(["B", "A", "A"])
        self.assertEqual(1, sum(command.endswith(" A") for command in commands))
        self.assertTrue(commands[-2].endswith(" A"))
        self.assertTrue(commands[-1].endswith(" B"))

    def test_target_pack_caps_the_delta(self):
        rows = [{"signature_update_number": n, "signature_name": f"S{n}"} for n in (10, 11, 12, 13)]
        selected = select_delta_rows(rows, 10, target_pack=12)
        self.assertEqual([11, 12], [row["signature_update_number"] for row in selected])

    def test_retired_section_states_when_unchecked(self):
        self.assertIn("not checked", retired_section(None, 1, 2)[0])

    def test_retired_section_lists_names_as_comments(self):
        lines = retired_section(["OLD:ONE", "OLD:TWO"], 1, 2)
        self.assertIn(": 2", lines[0])
        self.assertIn("# OLD:ONE", lines)
        self.assertTrue(all(line.startswith("#") for line in lines))


def make_workbook(path: Path) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "signatures"
    sheet.append(["signature_update_number", "signature_name", "signature_severity", "signature_release_date"])
    for number in (10, 11, 12, 13):
        sheet.append([number, f"SIG{number}", "Major", "2024-01-01"])
    workbook.save(path)


class ReportTests(unittest.TestCase):
    def report(self, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "signature.xlsx"
            make_workbook(source)
            path, _, count = create_delta_report(source, 10, Path(tmp), **kwargs)
            return path.name, path.read_text(), count

    def test_target_pack_names_files_and_limits_commands(self):
        name, text, count = self.report(target_pack=12)
        self.assertEqual("sig_delta_report_10_12.txt", name)
        self.assertEqual(2, count)
        self.assertIn("SIG12", text)
        self.assertNotIn("SIG13", text)
        self.assertIn("Target signature pack is 12", text)

    def test_rejects_bad_target_pack(self):
        for target in (10, 99):
            with self.assertRaises(ValueError):
                self.report(target_pack=target)

    def test_names_missing_from_target_pack_are_excluded(self):
        _, text, count = self.report(target_pack=12, pack_names={"SIG11"})
        self.assertEqual(1, count)
        self.assertIn("group-members SIG11", text)
        self.assertNotIn("group-members SIG12", text)
        self.assertIn("# SIG12", text)

    def test_report_includes_retired(self):
        _, text, _ = self.report(retired=["GONE:ONE"])
        self.assertIn("# GONE:ONE", text)


if __name__ == "__main__":
    unittest.main()

