"""CLI and CSV edge cases, including the bundled 2026-11-17 snapshot."""

from collections import Counter
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().with_name("ore_dimension_optimizer.py")


class CLIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--settings", str(self.folder / "settings.json"), *map(str, arguments)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

    def run_report(self, *arguments):
        prefix = self.folder / "report"
        process = self.run_cli(*arguments, "--report-prefix", prefix)
        self.assertIn(process.returncode, (0, 2), process.stderr)
        report = json.loads(prefix.with_suffix(".json").read_text(encoding="utf-8"))
        with Path(str(prefix) + "_coverage.csv").open(encoding="utf-8-sig", newline="") as handle:
            coverage = list(csv.DictReader(handle))
        return process, report, coverage

    def write_csv(self, rows):
        path = self.folder / "input.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows(rows)
        return path

    def test_default_snapshot_and_coverage_export(self):
        process, report, rows = self.run_report("--all-solutions")
        self.assertEqual(process.returncode, 0)
        self.assertEqual(report["result"]["minimum_count"], 12)
        self.assertEqual(report["result"]["optimal_solution_count"], 14)
        self.assertEqual(report["target_scope"], "all obtainable ores only")
        self.assertEqual(report["listed_ore_count"], 319)
        self.assertEqual(report["obtainable_ore_count"], 261)
        self.assertEqual(report["unobtainable_ore_count"], 58)
        self.assertEqual(len(rows), 319)
        self.assertEqual(Counter(row["Status"] for row in rows), {"Covered": 261, "Unobtainable": 58})
        self.assertIn("Full coverage is IMPOSSIBLE", process.stdout)
        self.assertIn("Covered target: 261 / 261 ores", process.stdout)
        for row in rows:
            if row["Status"] == "Covered":
                self.assertTrue(row["Selected dimensions"])
            else:
                self.assertFalse(row["All allowed source dimensions"])

    def test_strict_snapshot_is_explicitly_infeasible(self):
        process, report, _ = self.run_report("--strict")
        self.assertEqual(process.returncode, 2)
        self.assertEqual(report["target_ore_count"], 319)
        self.assertFalse(report["result"]["feasible"])
        self.assertIsNone(report["result"]["minimum_count"])
        self.assertEqual(report["result"]["solutions"], [])
        self.assertEqual(len(report["result"]["uncovered_ores"]), 58)
        self.assertIn("No minimum is reported", process.stdout)

    def test_additional_exclusion_and_tier_filter(self):
        for arguments, reachable, unavailable, minimum, candidate_count in (
            (["--exclude", "Toxic Everglades"], 221, 98, 11, 40),
            (["--max-tier", "3"], 176, 143, 9, 14),
        ):
            with self.subTest(arguments=arguments):
                process, report, rows = self.run_report(*arguments)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(report["obtainable_ore_count"], reachable)
                self.assertEqual(report["unobtainable_ore_count"], unavailable)
                self.assertEqual(report["result"]["minimum_count"], minimum)
                self.assertEqual(len(report["candidate_dimensions"]), candidate_count)
                self.assertEqual(Counter(row["Status"] for row in rows), {"Covered": reachable, "Unobtainable": unavailable})
                self.assertNotIn("Deep Dark (T10)", report["candidate_dimensions"])
                if "--exclude" in arguments:
                    self.assertNotIn("Toxic Everglades (T6)", report["candidate_dimensions"])
                else:
                    self.assertTrue(all(int(name.rsplit("(T", 1)[1][:-1]) <= 3 for name in report["candidate_dimensions"]))

    def test_zero_blank_and_tiny_positive_weights(self):
        path = self.write_csv([
            ["Ore", "World (T0)", "Other (T1)", "Deep Dark (T10)"],
            ["Tiny", "1e-400", "0", "0"],
            ["Blank", "", "1", "0"],
            ["Zero", "0", "", "1"],
            ["SUM", "1e-400", "1", "1"],
        ])
        process, report, rows = self.run_report("--csv", path)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(report["listed_ore_count"], 3)
        self.assertEqual(report["obtainable_ore_count"], 2)
        self.assertEqual(report["unobtainable_ores"], ["Zero"])
        self.assertEqual(report["result"]["minimum_count"], 2)
        self.assertEqual(report["summary_rows_skipped"], [5])
        self.assertEqual({row["Ore"] for row in rows}, {"Tiny", "Blank", "Zero"})

    def test_bad_input_fails_with_actionable_error(self):
        cases = [
            ([["Ore", "World"], ["A", "1"], [" a ", "1"]], "duplicate ore"),
            ([["Ore", "World", " world "], ["A", "1", "1"]], "headers must be unique"),
            ([["Ore", "World"], ["A", "1"], ["SUM", "2"]], "ore rows sum to"),
            ([["Ore", "World"], ["A", "1", "2"]], "expected 2 columns"),
        ]
        for value in ("not-a-number", "-0.5", "NaN", "Infinity"):
            cases.append(([["Ore", "World"], ["A", value]], "weight"))
        for rows, expected in cases:
            with self.subTest(rows=rows):
                path = self.write_csv(rows)
                process = self.run_cli("--csv", path)
                self.assertEqual(process.returncode, 1)
                self.assertIn(expected, process.stderr)
                self.assertNotIn("Traceback", process.stderr)


if __name__ == "__main__":
    unittest.main()
