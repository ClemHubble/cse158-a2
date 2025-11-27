"""
Batch client for the Dockerized DDC server.

Usage:
1) Start the Docker container (once) in another shell:
   docker run --rm -p 8080:80 chrisdonahue/ddc:latest
2) Run this script to send every *.ogg under ddc/data/raw to the server and
   save the returned .sm charts into ./ai_generated_sm.

Environment variables:
  DDC_SERVER_URL   Override server URL (default http://localhost:8080/choreograph)
  DDC_DIFF         Difficulty to request (default Medium; must be one of
                   Beginner, Easy, Medium, Hard, Challenge)
"""

import io
import os
import zipfile
from pathlib import Path

try:
    import requests
except ImportError:
    raise SystemExit("The requests package is required to run this client.")

SERVER_URL = os.environ.get("DDC_SERVER_URL", "http://localhost:8080/choreograph")
DIFF = os.environ.get("DDC_DIFF", "Medium")

RAW_DIR = Path("ddc") / "data" / "raw"
OUTPUT_DIR = Path.cwd() / "ai_generated_sm"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_for_file(ogg_path: Path) -> None:
    rel_path = ogg_path.relative_to(RAW_DIR)
    out_name = rel_path.as_posix().replace("/", "").replace("\\", "").replace(".ogg", "_auto.sm")
    song_title = ogg_path.stem
    song_artist = ogg_path.parent.name

    print(f"Processing {ogg_path} -> {OUTPUT_DIR / out_name}")

    with ogg_path.open("rb") as f:
        resp = requests.post(
            SERVER_URL,
            data={
                "song_artist": song_artist,
                "song_title": song_title,
                "diff_coarse": DIFF,
            },
            files={"audio_file": (ogg_path.name, f, "audio/ogg")},
            timeout=300,
        )

    if resp.status_code != 200:
        print(f"  Failed ({resp.status_code}): {resp.text}")
        return

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            sm_names = [name for name in zf.namelist() if name.lower().endswith(".sm")]
            if not sm_names:
                print("  No .sm found in server response")
                return
            sm_bytes = zf.read(sm_names[0])
    except zipfile.BadZipFile:
        print("  Server response was not a valid zip file")
        return

    out_fp = OUTPUT_DIR / out_name
    out_fp.write_bytes(sm_bytes)
    print(f"  Saved {out_fp}")


def main() -> None:
    if not RAW_DIR.exists():
        raise SystemExit(f"Raw audio directory not found: {RAW_DIR}")

    ogg_files = sorted(RAW_DIR.rglob("*.ogg"))
    if not ogg_files:
        print(f"No .ogg files found under {RAW_DIR}")
        return

    for ogg_fp in ogg_files:
        generate_for_file(ogg_fp)


if __name__ == "__main__":
    main()
