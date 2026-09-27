import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml


path = Path(__file__).resolve().parents[1] / "tools/configure-wanxiang.py"
spec = importlib.util.spec_from_file_location("typing_tools", path)
typing_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(typing_tools)


class TypingToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.user = Path(self.temp.name)
        (self.user / "build").mkdir()
        self.write("build/wanxiang.schema.yaml", {
            "speller": {"algebra": ["xlit/①②③④/7890"]},
            "translator": {"dictionary": "wanxiang", "user_dict": "learned_words"},
        })
        self.write("wanxiang.dict.yaml", {"name": "wanxiang", "import_tables": ["dicts/chars", "dicts/base"]})

    def write(self, name, value):
        (self.user / name).write_text(yaml.safe_dump(value, allow_unicode=True), encoding="utf-8")

    def test_patch_preserves_existing_settings_and_is_idempotent(self):
        self.write("wanxiang.custom.yaml", {"patch": {"menu/page_size": 9}})
        first = typing_tools.prepare(self.user)
        (self.user / "wanxiang.custom.yaml").write_text(first["wanxiang.custom.yaml"], encoding="utf-8")
        self.assertEqual(first, typing_tools.prepare(self.user))
        self.assertEqual(yaml.safe_load(first["wanxiang.custom.yaml"])["patch"]["menu/page_size"], 9)

    def test_dictionary_keeps_learning_and_source_tables(self):
        source = self.user / "domain.dict.yaml"
        source.write_text('---\nname: domain\n...\n测试词\tce shi ci\t999999\n', encoding="utf-8")
        files = typing_tools.prepare(self.user, source)
        patch = yaml.safe_load(files["wanxiang.custom.yaml"])["patch"]
        self.assertEqual(patch["translator/user_dict"], "learned_words")
        self.assertEqual(yaml.safe_load(files["wanxiang_extended.dict.yaml"])["import_tables"],
                         ["dicts/chars", "dicts/base", "user_extension"])
        self.assertIn("测试词\tce shi ci\t1000", files["user_extension.dict.yaml"])
        self.assertFalse((self.user / "wanxiang.custom.yaml").exists())

    def test_rejects_dependencies_missing_codes_and_invalid_weights(self):
        for data in (
            '---\nname: bad\nimport_tables: [../private]\n...\n',
            '---\nname: bad\n...\n没有拼音\n',
            '---\nname: bad\n...\n测试\tce shi\t1e999\n',
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                typing_tools.import_dictionary(data)

    def test_rejects_wrong_patch_type_and_insecure_url(self):
        self.write("wanxiang.custom.yaml", {"patch": []})
        with self.assertRaises(ValueError):
            typing_tools.prepare(self.user)
        self.write("wanxiang.custom.yaml", {"patch": {}})
        with self.assertRaises(ValueError):
            typing_tools.prepare(self.user, dictionary_url="http://example.invalid/dict.yaml")


if __name__ == "__main__":
    unittest.main()
