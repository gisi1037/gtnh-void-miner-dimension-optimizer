"""Persistent tier settings, one-run overrides, and launcher input."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().with_name("ore_dimension_optimizer.py")


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.settings = self.folder / "settings.json"
        self.prefix = self.folder / "report"

    def run_cli(self, *arguments, input_text=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--settings", str(self.settings),
             "--report-prefix", str(self.prefix), *map(str, arguments)],
            input=input_text, capture_output=True, encoding="utf-8", timeout=30,
        )

    def read_report(self):
        return json.loads(self.prefix.with_suffix(".json").read_text(encoding="utf-8"))

    def test_save_and_reuse_tier(self):
        first = self.run_cli("--set-tier", "3")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(self.settings.read_text()), {"max_rocket_tier": 3})
        second = self.run_cli()
        self.assertEqual(second.returncode, 0, second.stderr)
        report = self.read_report()
        self.assertEqual(report["max_rocket_tier"], 3)
        self.assertEqual(report["obtainable_ore_count"], 176)
        self.assertEqual(report["unobtainable_ore_count"], 143)
        self.assertEqual(report["result"]["minimum_count"], 9)
        self.assertNotIn("Deep Dark (T10)", report["candidate_dimensions"])
        self.assertTrue(all(int(name.rsplit("(T", 1)[1][:-1]) <= 3
                            for name in report["candidate_dimensions"]))

    def test_override_does_not_modify_saved_setting(self):
        self.settings.write_text('{"max_rocket_tier": 3}')
        before = self.settings.read_bytes()
        for override in ("all", "0"):
            process = self.run_cli("--max-tier", override)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(self.settings.read_bytes(), before)
            report = self.read_report()
            self.assertEqual(report["max_rocket_tier"], None if override == "all" else 0)
            if override == "all":
                self.assertEqual(report["obtainable_ore_count"], 261)
            else:
                self.assertEqual(len(report["candidate_dimensions"]), 4)

    def test_reset_to_unlimited(self):
        self.settings.write_text('{"max_rocket_tier": 0}')
        process = self.run_cli("--set-tier", "all")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIsNone(json.loads(self.settings.read_text())["max_rocket_tier"])
        self.assertIsNone(self.read_report()["max_rocket_tier"])
        self.assertEqual(self.read_report()["result"]["minimum_count"], 12)
        self.assertNotIn("Deep Dark (T10)", self.read_report()["candidate_dimensions"])

    def test_missing_settings_defaults_to_unlimited(self):
        process = self.run_cli()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertFalse(self.settings.exists())
        self.assertIsNone(self.read_report()["max_rocket_tier"])

    def test_invalid_settings_are_not_silently_ignored(self):
        for value in ('{', '[]', '{"max_rocket_tier": true}',
                      '{"max_rocket_tier": -1}', '{"max_rocket_tier": "3"}',
                      '{"max_rocket_tier": 3.5}', '{"max_rockt_tier": 3}'):
            with self.subTest(value=value):
                self.settings.write_text(value)
                process = self.run_cli()
                self.assertEqual(process.returncode, 1)
                self.assertIn("Error:", process.stderr)
                self.assertNotIn("Traceback", process.stderr)
                self.assertEqual(self.settings.read_text(), value)

    def test_invalid_cli_tiers_and_conflicting_options(self):
        for arguments in (("--set-tier", "-1"), ("--max-tier", "3.5"),
                          ("--set-tier", "bad"),
                          ("--max-tier", "3", "--set-tier", "2")):
            with self.subTest(arguments=arguments):
                process = self.run_cli(*arguments)
                self.assertEqual(process.returncode, 2)
                self.assertFalse(self.settings.exists())

    def test_interactive_save_retry_and_keep(self):
        process = self.run_cli("--choose-tier", input_text="invalid\n3\n")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("Invalid tier:", process.stdout)
        self.assertEqual(self.read_report()["max_rocket_tier"], 3)
        before = self.settings.read_bytes()
        process = self.run_cli("--choose-tier", input_text="\n")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertEqual(self.read_report()["max_rocket_tier"], 3)

    def test_interactive_eof_fails_cleanly(self):
        process = self.run_cli("--choose-tier", input_text="")
        self.assertEqual(process.returncode, 1)
        self.assertIn("--set-tier N", process.stderr)
        self.assertFalse(self.settings.exists())

    def test_strict_respects_saved_tier(self):
        self.settings.write_text('{"max_rocket_tier": 3}')
        process = self.run_cli("--strict")
        self.assertEqual(process.returncode, 2, process.stderr)
        self.assertFalse(self.read_report()["result"]["feasible"])
        self.assertEqual(self.read_report()["unobtainable_ore_count"], 143)


if __name__ == "__main__":
    unittest.main()
