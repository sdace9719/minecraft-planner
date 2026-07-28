"""Generate constants/stack_sizes.json from mcmeta summary data.

Usage:
    uv run python scripts/generate_stack_sizes.py                # default 1.21.11
    uv run python scripts/generate_stack_sizes.py --version 1.21
"""
import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "constants" / "stack_sizes.json"
MCMETA_REPO = "misode/mcmeta"


def download_zip_entry(owner_repo: str, ref: str, entry_suffix: str) -> bytes:
    url = f"https://codeload.github.com/{owner_repo}/zip/{ref}"
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for name in zf.namelist():
            if name.endswith(entry_suffix):
                return zf.read(name)
    raise FileNotFoundError(f"No entry matching *{entry_suffix} in {owner_repo}@{ref}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate stack_sizes.json from mcmeta")
    parser.add_argument("--version", default="1.21.11", help="Minecraft version (default: 1.21.11)")
    args = parser.parse_args()

    mcmeta_ref = f"{args.version}-summary"
    print(f"Downloading item components from {MCMETA_REPO}@{mcmeta_ref} ...")

    try:
        raw = download_zip_entry(MCMETA_REPO, mcmeta_ref, "item_components/data.min.json")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(raw)
    exceptions: dict[str, int] = {}
    for item_name, components in data.items():
        ss = components.get("minecraft:max_stack_size", 64)
        if ss != 64:
            exceptions[item_name] = ss

    OUT_PATH.write_text(json.dumps(exceptions, indent=2) + "\n", encoding="utf-8")
    total = len(data)
    print(f"Processed {total} items -> {len(exceptions)} non-64 exceptions")
    print(f"Written: {OUT_PATH}")


if __name__ == "__main__":
    main()
