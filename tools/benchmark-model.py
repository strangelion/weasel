"""Compare an installed grammar model with a model-free isolated schema.

Requires PyYAML and the native model-benchmark executable. Never deploys to the
installed input method or reads its user dictionaries/history.
"""

import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import statistics
import subprocess

import yaml


def resource_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(f"Unsupported resource name: {value!r}")
    return value


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", required=True, type=Path)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--user-data", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--schema", default="wanxiang")
    parser.add_argument("--corpus", type=Path, default=(
        Path(__file__).resolve().parents[1] / "test/data/model-pinyin.tsv"))
    args = parser.parse_args()
    schema_id = resource_name(args.schema)
    compiled_path = args.user_data / "build" / f"{schema_id}.schema.yaml"
    original = yaml.safe_load(compiled_path.read_text(encoding="utf-8-sig"))
    translator = copy.deepcopy(original["translator"])
    dictionary = resource_name(translator["dictionary"])
    prism = resource_name(translator.get("prism", dictionary))
    grammar = original.get("grammar")
    if not grammar or not grammar.get("language"):
        raise ValueError("The selected deployed schema has no grammar model.")
    model = resource_name(grammar["language"])
    sources = {
        f"{dictionary}.table.bin": args.user_data / "build" / f"{dictionary}.table.bin",
        f"{prism}.prism.bin": args.user_data / "build" / f"{prism}.prism.bin",
    }
    model_path = args.user_data / f"{model}.gram"
    for required in [args.dll, args.runner, args.corpus, model_path, *sources.values()]:
        if not required.is_file():
            raise FileNotFoundError(required)

    # Require a new destination so existing data can never be overwritten.
    root = args.work_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    shared = root / "shared"
    build = shared / "build"
    build.mkdir(parents=True)
    for name, source in sources.items():
        shutil.copy2(source, build / name)
    shutil.copy2(model_path, shared / model_path.name)
    translator["enable_user_dict"] = False
    translator["contextual_suggestions"] = False
    translator["prism"] = prism
    # Use the same dictionary, spelling rules and candidate search in both runs.
    # Exclude optional Lua/UI features to isolate the grammar model contribution.
    base = {
        "schema": {"schema_id": "model_baseline", "name": "Model baseline"},
        "engine": {
            "processors": ["ascii_composer", "speller", "selector", "navigator", "express_editor"],
            "segmentors": ["ascii_segmentor", "abc_segmentor", "fallback_segmentor"],
            "translators": ["script_translator"],
            "filters": ["uniquifier"],
        },
        "speller": copy.deepcopy(original["speller"]),
        "translator": translator,
        "menu": {"page_size": 5},
        "ascii_composer": {"switch_key": {"Shift_L": "noop", "Shift_R": "noop"}},
    }
    profiles = ("model_baseline", "model_enabled")
    for profile in profiles:
        config = copy.deepcopy(base)
        config["schema"]["schema_id"] = profile
        if profile == "model_enabled":
            config["grammar"] = copy.deepcopy(grammar)
        (build / f"{profile}.schema.yaml").write_text(
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (build / "default.yaml").write_text(yaml.safe_dump({
        "schema_list": [{"schema": profiles[0]}],
    }), encoding="utf-8")

    summary = {
        "scope": "Synthetic smoke test; no claim of general accuracy or UI latency",
        "schema": schema_id,
        "model": model,
        "model_bytes": model_path.stat().st_size,
        "model_sha256": sha256_file(model_path),
        "profiles": {},
    }
    for profile in profiles:
        result = root / f"{profile}.tsv"
        subprocess.run([
            str(args.runner.resolve()), str(args.dll.resolve()), str(root),
            profile, str(args.corpus.resolve()), str(result),
        ], check=True, timeout=180, cwd=root)
        with result.open(encoding="utf-8") as stream:
            metadata = stream.readline().strip()
            rows = list(csv.DictReader(stream, delimiter="\t"))
        if not rows or any(not row["top1"] for row in rows):
            raise RuntimeError(f"{profile}: missing candidates; inspect logs before comparing")
        first_round = [row for row in rows if row["round"] == "1"]
        summary["profiles"][profile] = {
            "metadata": metadata,
            "sentences": len(first_round),
            "top1_exact": sum(row["expected"] == row["top1"] for row in first_round),
            "top5_exact": sum(row["top5_hit"] == "1" for row in first_round),
            "median_sentence_key_p50_ms": statistics.median(float(row["key_p50_ms"]) for row in rows),
            "median_sentence_key_p95_ms": statistics.median(float(row["key_p95_ms"]) for row in rows),
        }
    report = json.dumps(summary, ensure_ascii=False, indent=2)
    (root / "summary.json").write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
