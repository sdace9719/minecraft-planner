import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

import requests


MCMETA_REPO = "misode/mcmeta"


def download_zip(owner_repo: str, ref: str) -> bytes:
    url = f"https://codeload.github.com/{owner_repo}/zip/{ref}"
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return resp.content


def extract_subset(zip_bytes: bytes, *, src_prefix: str, dest_root: Path, rel_paths: list[str]) -> None:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        for rel in rel_paths:
            want_prefix = f"{src_prefix}/{rel}".rstrip("/") + "/"
            for name in names:
                if not name.startswith(want_prefix):
                    continue
                if name.endswith("/"):
                    continue
                out_path = dest_root / name[len(src_prefix) + 1 :]
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, out_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: uv run python scripts/vendor_mcmeta_data_json.py <mcmeta_ref> <dest_dir>",
            file=sys.stderr,
        )
        sys.exit(1)

    mcmeta_ref = sys.argv[1]
    dest_dir = Path(sys.argv[2]).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    zip_bytes = download_zip(MCMETA_REPO, mcmeta_ref)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        top = zf.namelist()[0].split("/", 1)[0]

    # mcmeta data-json tree layout: data/minecraft/...
    rel_paths = [
        "data/minecraft/recipe",
        "data/minecraft/tags/item",
        "data/minecraft/worldgen/placed_feature",
        "data/minecraft/worldgen/configured_feature",
        "data/minecraft/worldgen/biome",
    ]

    extract_subset(zip_bytes, src_prefix=top, dest_root=dest_dir, rel_paths=rel_paths)

    (dest_dir / "MANIFEST.json").write_text(
        json.dumps(
            {
                "source_repo": f"https://github.com/{MCMETA_REPO}",
                "source_ref": mcmeta_ref,
                "included_paths": rel_paths,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Vendored {MCMETA_REPO}@{mcmeta_ref} into {dest_dir}")


if __name__ == "__main__":
    main()

