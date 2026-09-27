"""Prepare a reversible full-pinyin fix and optional explicit-pinyin dictionary.

Requires PyYAML. No background network access or automatic Rime deployment.
"""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

import yaml


# These non-Mandarin syllables otherwise shadow common abbreviated phrases.
# Keep nun: it is a legitimate Mandarin reading of a rare character.
SPELLING_RULE = "erase/^(bun|ceok|ceon|dim|din|tii)[7890]?$/"


def read_yaml(path):
    value = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping: {path.name}")
    return value


def import_dictionary(text):
    lines = text.splitlines()
    end = next((i for i, line in enumerate(lines) if line.strip() == "..."), None)
    if end is None:
        raise ValueError("Dictionary must have a YAML header ending with '...'.")
    header = yaml.safe_load("\n".join(lines[:end]))
    if not isinstance(header, dict) or header.get("import_tables"):
        raise ValueError("Import a standalone dictionary with explicit pinyin.")
    if header.get("columns", ["text", "code", "weight"]) != ["text", "code", "weight"]:
        raise ValueError("Supported columns are text, code, weight (optional).")
    entries = {}
    for number, line in enumerate(lines[end + 1:], end + 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("\t")
        if (len(fields) not in (2, 3) or not fields[0].strip()
                or not re.fullmatch(r"[a-z]+(?: [a-z]+)*", fields[1])):
            raise ValueError(f"Line {number}: expected text and space-separated lowercase pinyin.")
        if any(ord(c) < 32 for c in fields[0]):
            raise ValueError(f"Line {number}: control character in text.")
        weight = fields[2] if len(fields) == 3 else "100"
        if not re.fullmatch(r"[0-9]{1,9}", weight):
            raise ValueError(f"Line {number}: weight must be a nonnegative integer.")
        # Keep imported counts from overpowering the curated main dictionary.
        entries[(fields[0], fields[1])] = max(1, min(int(weight), 1000))
    if not entries:
        raise ValueError("Dictionary has no entries.")
    notices = [line for line in lines[:end] if line.lstrip().startswith("#")]
    output = [*notices, "# Imported locally; see lexicon-source.json for provenance.", "---",
              "name: user_extension", 'version: "1"', "sort: by_weight", "..."]
    output.extend(f"{word}\t{code}\t{weight}" for (word, code), weight in entries.items())
    return "\n".join(output) + "\n", len(entries)


def prepare(user, dictionary=None, dictionary_url=None):
    # Restrict this patch to the installed full-pinyin configuration it targets.
    compiled = read_yaml(user / "build/wanxiang.schema.yaml")
    algebra = compiled.get("speller", {}).get("algebra", [])
    if not isinstance(algebra, list) or "xlit/①②③④/7890" not in algebra:
        raise ValueError("Unsupported Wanxiang spelling rules; inspect the schema before patching.")
    if any(isinstance(rule, str) and rule.startswith("xform/") and "$2$1" in rule for rule in algebra):
        raise ValueError("This patch is for full pinyin, not double pinyin.")
    custom_path = user / "wanxiang.custom.yaml"
    custom = read_yaml(custom_path) if custom_path.exists() else {}
    custom = copy.deepcopy(custom)
    patch = custom.setdefault("patch", {})
    if not isinstance(patch, dict):
        raise ValueError("Existing custom patch must be a mapping.")
    rules = patch.setdefault("speller/algebra/+", [])
    if not isinstance(rules, list):
        raise ValueError("Existing speller/algebra/+ must be a list.")
    if SPELLING_RULE not in rules:
        rules.append(SPELLING_RULE)
    files = {}
    if dictionary or dictionary_url:
        source = {"source_file": dictionary.name if dictionary else "network.dict.yaml"}
        if dictionary_url:
            url = urlsplit(dictionary_url)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("Use a public HTTPS dictionary URL without embedded credentials.")
            with urlopen(dictionary_url, timeout=30) as response:
                if urlsplit(response.url).scheme != "https":
                    raise ValueError("Dictionary download redirected away from HTTPS.")
                data = response.read(20 * 1024 * 1024 + 1)
            if len(data) > 20 * 1024 * 1024:
                raise ValueError("Dictionary exceeds the 20 MiB download limit.")
            source["source_url"] = urlunsplit((url.scheme, url.netloc, url.path, "", ""))
        else:
            data = dictionary.read_bytes()
        imported, count = import_dictionary(data.decode("utf-8-sig"))
        base = read_yaml(user / "wanxiang.dict.yaml")
        tables = base.get("import_tables")
        if not isinstance(tables, list) or not tables:
            raise ValueError("The installed Wanxiang dictionary has no import_tables.")
        current = compiled.get("translator", {}).get("dictionary")
        if current not in ("wanxiang", "wanxiang_extended"):
            raise ValueError("A different custom dictionary is active; merge it manually first.")
        base["name"] = "wanxiang_extended"
        base["import_tables"] = [*tables, "user_extension"]
        files["user_extension.dict.yaml"] = imported
        files["wanxiang_extended.dict.yaml"] = yaml.safe_dump(
            base, allow_unicode=True, sort_keys=False, explicit_start=True, explicit_end=True)
        patch["translator/dictionary"] = "wanxiang_extended"
        patch["translator/prism"] = "wanxiang_extended"
        # Changing the dictionary must not detach the existing learned words.
        patch["translator/user_dict"] = compiled["translator"].get("user_dict", current)
        files["lexicon-source.json"] = json.dumps({
            **source,
            "sha256": hashlib.sha256(data).hexdigest(),
            "entries": count,
            "imported_utc": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2) + "\n"
    files["wanxiang.custom.yaml"] = yaml.safe_dump(custom, allow_unicode=True, sort_keys=False)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-data", type=Path, required=True)
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--dictionary", type=Path, help="Standalone Rime dictionary, e.g. converted SCEL")
    sources.add_argument("--dictionary-url", help="Download an explicit-pinyin Rime dictionary over HTTPS")
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory for preview and backups")
    parser.add_argument("--apply", action="store_true", help="Back up originals and install prepared files")
    args = parser.parse_args()
    files = prepare(args.user_data, args.dictionary, args.dictionary_url)
    original = {name: (args.user_data / name).read_bytes() if (args.user_data / name).exists() else None
                for name in files}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        (args.output_dir / name).write_text(content, encoding="utf-8")
    if args.apply:
        backup = args.output_dir / "backup"
        backup.mkdir()
        for name, data in original.items():
            if data is not None:
                (backup / name).write_bytes(data)
        (backup / "manifest.json").write_text(json.dumps({
            "new_files": [name for name, data in original.items() if data is None],
            "replaced_files": [name for name, data in original.items() if data is not None],
        }, indent=2), encoding="utf-8")
        for name, data in original.items():
            current = (args.user_data / name).read_bytes() if (args.user_data / name).exists() else None
            if current != data:
                raise RuntimeError("Configuration changed during preparation; nothing applied.")
        # Stage dependencies first, then atomically replace the custom patch last.
        # Rime continues using its deployed build until the user redeploys.
        for name in files:
            target = args.user_data / name
            staging = target.with_name(target.name + ".typing-tmp")
            with staging.open("xb") as stream:
                stream.write((args.output_dir / name).read_bytes())
            staging.replace(target)
        print("Applied. Redeploy Rime to activate; originals are in output-dir/backup.")
    else:
        print("Prepared only. Review the output, then use a new output-dir with --apply.")


if __name__ == "__main__":
    main()
