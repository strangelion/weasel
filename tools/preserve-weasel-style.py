"""Preserve the effective Weasel style in a safe user customization file.

Requires PyYAML. Color values are emitted as quoted eight-digit hex strings;
plain integer zero is opaque black in Weasel, while 0x00000000 is transparent.
"""

import argparse
import copy
from pathlib import Path

import yaml


class QuotedHex(str):
    pass


def quoted_hex_representer(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="'")


yaml.SafeDumper.add_representer(QuotedHex, quoted_hex_representer)


def read_mapping(path):
    value = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping: {path.name}")
    return value


def encode_colors(value, key=""):
    if isinstance(value, dict):
        return {name: encode_colors(item, name) for name, item in value.items()}
    if key.endswith("_color"):
        if isinstance(value, int) and 0 <= value <= 0xFFFFFFFF:
            return QuotedHex(f"0x{value:08X}")
        if isinstance(value, str) and value.lower().startswith("0x"):
            parsed = int(value, 16)
            if 0 <= parsed <= 0xFFFFFFFF:
                return QuotedHex(f"0x{parsed:08X}")
        raise ValueError(f"Invalid color value for {key}: {value!r}")
    return copy.deepcopy(value)


def prepare(user):
    effective = read_mapping(user / "build/weasel.yaml")
    style = effective.get("style")
    schemes = effective.get("preset_color_schemes")
    if not isinstance(style, dict) or not isinstance(schemes, dict):
        raise ValueError("The deployed Weasel configuration has no style data.")
    names = {style.get("color_scheme"), style.get("color_scheme_dark")}
    names.discard(None)
    if not names or any(name not in schemes for name in names):
        raise ValueError("The active color scheme is missing from the deployed configuration.")
    custom_path = user / "weasel.custom.yaml"
    custom = read_mapping(custom_path) if custom_path.exists() else {}
    custom = copy.deepcopy(custom)
    patch = custom.setdefault("patch", {})
    if not isinstance(patch, dict):
        raise ValueError("Existing custom patch must be a mapping.")
    for name in list(patch):
        if name == "style" or name.startswith("style/"):
            del patch[name]
    patch["style"] = encode_colors(style)
    for name in sorted(names):
        patch.pop(f"preset_color_schemes/{name}", None)
        patch[f"preset_color_schemes/{name}"] = encode_colors(schemes[name])
    return yaml.safe_dump(custom, allow_unicode=True, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New preview file")
    parser.add_argument("--apply", action="store_true", help="Replace weasel.custom.yaml after making a backup")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    content = prepare(args.user_data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    if args.apply:
        target = args.user_data / "weasel.custom.yaml"
        backup = args.output.with_suffix(args.output.suffix + ".previous")
        if target.exists():
            backup.write_bytes(target.read_bytes())
        staging = target.with_name(target.name + ".style-tmp")
        with staging.open("xb") as stream:
            stream.write(args.output.read_bytes())
        staging.replace(target)
        print(f"Applied; previous file: {backup if backup.exists() else 'not present'}")
    else:
        print("Prepared only. Review the output and rerun with a new output plus --apply.")


if __name__ == "__main__":
    main()
