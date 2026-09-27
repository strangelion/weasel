import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml


path = Path(__file__).resolve().parents[1] / "tools/preserve-weasel-style.py"
spec = importlib.util.spec_from_file_location("weasel_style", path)
weasel_style = importlib.util.module_from_spec(spec)
spec.loader.exec_module(weasel_style)


class WeaselStyleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.user = Path(self.temp.name)
        (self.user / "build").mkdir()
        deployed = {
            "style": {"color_scheme": "custom", "font_point": 14},
            "preset_color_schemes": {"custom": {
                "back_color": 0,
                "candidate_text_color": 0xFF4A4A4A,
                "name": "Custom",
            }},
        }
        (self.user / "build/weasel.yaml").write_text(
            yaml.safe_dump(deployed), encoding="utf-8")

    def test_transparent_zero_remains_eight_digit_hex_string(self):
        output = weasel_style.prepare(self.user)
        self.assertIn("back_color: '0x00000000'", output)
        self.assertIn("candidate_text_color: '0xFF4A4A4A'", output)
        parsed = yaml.safe_load(output)
        scheme = parsed["patch"]["preset_color_schemes/custom"]
        self.assertEqual(scheme["back_color"], "0x00000000")

    def test_preserves_unrelated_patch(self):
        (self.user / "weasel.custom.yaml").write_text(
            yaml.safe_dump({"patch": {
                "app_options/test.exe/ascii_mode": True,
                "preset_color_schemes/another": {"back_color": "0xFFFFFFFF"},
            }}),
            encoding="utf-8")
        parsed = yaml.safe_load(weasel_style.prepare(self.user))
        self.assertTrue(parsed["patch"]["app_options/test.exe/ascii_mode"])
        self.assertEqual(
            parsed["patch"]["preset_color_schemes/another"]["back_color"],
            "0xFFFFFFFF")

    def test_rejects_invalid_active_color(self):
        deployed = yaml.safe_load((self.user / "build/weasel.yaml").read_text())
        deployed["preset_color_schemes"]["custom"]["back_color"] = -1
        (self.user / "build/weasel.yaml").write_text(yaml.safe_dump(deployed), encoding="utf-8")
        with self.assertRaises(ValueError):
            weasel_style.prepare(self.user)


if __name__ == "__main__":
    unittest.main()
