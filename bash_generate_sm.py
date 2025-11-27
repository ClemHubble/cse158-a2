"""
Batch client for the Dockerized DDC server that rewrites AI charts to match
the human .sm file format (header/layout). For each .ogg in ddc/data/raw:
* Reuse the human header (everything before #NOTES) if present; otherwise use
  a human-like fallback header.
* Request multiple difficulties from the server.
* Write one combined .sm per song into ./ai_generated_sm with human-style
  headers and the AI-generated #NOTES blocks.

Environment variables:
  DDC_SERVER_URL  (default http://localhost:8080/choreograph)
  DDC_DIFFS       Comma-separated difficulties to request
                  (default Beginner,Easy,Medium,Hard,Challenge)
"""

import io
import os
import re
import zipfile
from pathlib import Path
from typing import List, Tuple

try:
    import requests
except ImportError:
    raise SystemExit("The requests package is required to run this client.")

SERVER_URL = os.environ.get("DDC_SERVER_URL", "http://localhost:8080/choreograph")
DIFFS = [
    d.strip()
    for d in os.environ.get(
        "DDC_DIFFS", "Beginner,Easy,Medium,Hard,Challenge"
    ).split(",")
    if d.strip()
]

RAW_DIR = Path("ddc") / "data" / "raw"
OUTPUT_DIR = Path.cwd() / "ai_generated_sm"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_HEADER = """\
#TITLE:{title};
#SUBTITLE:;
#ARTIST:{artist};
#TITLETRANSLIT:;
#SUBTITLETRANSLIT:;
#ARTISTTRANSLIT:;
#GENRE:;
#CREDIT:DDC-AI;
#BANNER:bn.png;
#BACKGROUND:bg.png;
#LYRICSPATH:;
#CDTITLE:;
#MUSIC:{music};
#OFFSET:0.000;
#SAMPLESTART:0.000;
#SAMPLELENGTH:15.000;
#SELECTABLE:YES;
#BPMS:0.000=125.000;
#STOPS:;
#BGCHANGES:;
#KEYSOUNDS:;
#ATTACKS:;
"""


def read_human_header(human_sm: Path, fallback_title: str, fallback_artist: str, music_name: str) -> str:
    """Return the header (all lines before #NOTES) from the human file, or a fallback."""
    if not human_sm.exists():
        return DEFAULT_HEADER.format(title=fallback_title, artist=fallback_artist, music=music_name)
    lines = human_sm.read_text(errors="ignore").splitlines()
    header_lines: List[str] = []
    for ln in lines:
        if ln.lstrip().startswith("#NOTES"):
            break
        header_lines.append(ln.rstrip())
    if not header_lines:
        return DEFAULT_HEADER.format(title=fallback_title, artist=fallback_artist, music=music_name)
    return "\n".join(header_lines) + "\n"


def extract_notes(sm_bytes: bytes) -> List[str]:
    """Extract all #NOTES blocks (as text) from a .sm file."""
    text = sm_bytes.decode(errors="ignore")
    blocks: List[str] = []
    pattern = re.compile(r"#NOTES:\s*(.*?)\s*;", re.S)
    for match in pattern.finditer(text):
        block = match.group(1).strip()
        blocks.append("#NOTES:\n" + block + ";\n")
    return blocks


def build_output_sm(header: str, note_blocks: List[Tuple[str, str]]) -> str:
    """Combine header with #NOTES blocks, overriding difficulty labels."""
    out_blocks: List[str] = []
    for diff_label, raw_block in note_blocks:
        lines = raw_block.splitlines()
        if len(lines) >= 4:
            lines[3] = f"    {diff_label}:"
        out_blocks.append("\n".join(lines))
    return header + "\n".join(out_blocks)


def request_chart(ogg_path: Path, diff: str) -> bytes:
    """Call the DDC server for a single difficulty and return the .sm bytes."""
    with ogg_path.open("rb") as f:
        resp = requests.post(
            SERVER_URL,
            data={
                "song_artist": ogg_path.parent.name,
                "song_title": ogg_path.stem,
                "diff_coarse": diff,
            },
            files={"audio_file": (ogg_path.name, f, "audio/ogg")},
            timeout=300,
        )
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        sm_names = [n for n in zf.namelist() if n.lower().endswith(".sm")]
        if not sm_names:
            raise RuntimeError("No .sm found in server response")
        return zf.read(sm_names[0])


def process_song(ogg_path: Path) -> None:
    rel = ogg_path.relative_to(RAW_DIR)
    song_dir = ogg_path.parent
    human_sms = list(song_dir.glob("*.sm"))
    human_header = read_human_header(
        human_sms[0] if human_sms else Path(),
        ogg_path.stem,
        song_dir.name,
        ogg_path.name,
    )

    note_blocks: List[Tuple[str, str]] = []
    for diff in DIFFS:
        try:
            sm_bytes = request_chart(ogg_path, diff)
            blocks = extract_notes(sm_bytes)
            if not blocks:
                print(f"  [{diff}] no notes returned")
                continue
            note_blocks.append((diff, blocks[0]))
            print(f"  [{diff}] ok")
        except Exception as e:
            print(f"  [{diff}] failed: {e}")

    if not note_blocks:
        print("  no charts generated")
        return

    out_name = rel.as_posix().replace("/", "").replace("\\", "").replace(".ogg", "_auto.sm")
    out_path = OUTPUT_DIR / out_name
    out_path.write_text(build_output_sm(human_header, note_blocks))
    print(f"  saved {out_path}")


def main() -> None:
    if not RAW_DIR.exists():
        raise SystemExit(f"Raw audio directory not found: {RAW_DIR}")
    oggs = sorted(RAW_DIR.rglob("*.ogg"))
    if not oggs:
        print(f"No .ogg files found under {RAW_DIR}")
        return
    print(f"Found {len(oggs)} audio files; generating AI .sm with human-style headers")
    for ogg in oggs:
        print(f"Processing {ogg}")
        process_song(ogg)


if __name__ == "__main__":
    main()
