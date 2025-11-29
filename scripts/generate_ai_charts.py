#!/usr/bin/env python3
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from io import BytesIO

import requests
from tqdm import tqdm


DDC_SERVER_URL = os.environ.get("DDC_SERVER_URL", "http://localhost:8080")


def parse_sm_notes(notes_text: str) -> list[dict]:
    steps = []
    measures = notes_text.strip().split(',')

    beat = 0.0
    for measure_idx, measure in enumerate(measures):
        lines = [l.strip() for l in measure.strip().split(
            '\n') if l.strip() and not l.strip().startswith('//')]
        if not lines:
            continue

        subdivision = len(lines)
        beats_per_line = 4.0 / subdivision

        for line_idx, line in enumerate(lines):
            if line != '0000':
                steps.append({
                    'beat': beat,
                    'step': line
                })
            beat += beats_per_line

    return steps


def parse_sm_file(sm_content: str) -> dict:
    """Parse a StepMania .sm file into structured data."""
    result = {
        'title': None,
        'artist': None,
        'bpm': None,
        'charts': []
    }

    # Parse metadata
    title_match = re.search(r'#TITLE:([^;]*);', sm_content)
    if title_match:
        result['title'] = title_match.group(1).strip()

    artist_match = re.search(r'#ARTIST:([^;]*);', sm_content)
    if artist_match:
        result['artist'] = artist_match.group(1).strip()

    bpm_match = re.search(r'#BPMS:[\d.]*=([\d.]+);', sm_content)
    if bpm_match:
        result['bpm'] = float(bpm_match.group(1))

    # Parse notes sections
    notes_pattern = r'#NOTES:\s*([^:]*):([^:]*):([^:]*):([^:]*):([^:]*):([^;]*);'
    for match in re.finditer(notes_pattern, sm_content, re.DOTALL):
        chart_type = match.group(1).strip()
        author = match.group(2).strip()
        difficulty = match.group(3).strip()
        difficulty_num = match.group(4).strip()
        notes_text = match.group(6)

        if chart_type == 'dance-single':
            steps = parse_sm_notes(notes_text)
            result['charts'].append({
                'difficulty': difficulty,
                'difficulty_num': int(difficulty_num) if difficulty_num.isdigit() else 0,
                'steps': steps,
                'num_steps': len(steps)
            })

    return result


def find_audio_files(data_dir: Path) -> list[tuple[Path, str, str]]:
    """
    Find all audio files in the dataset.
    Returns list of (audio_path, dataset_name, song_name) tuples.
    """
    results = []
    raw_dir = data_dir / 'raw'

    for dataset in ['fraxtil', 'itg']:
        dataset_dir = raw_dir / dataset
        if not dataset_dir.exists():
            continue

        # Walk through pack directories
        for pack_dir in dataset_dir.iterdir():
            if not pack_dir.is_dir():
                continue

            # Each song is in its own subdirectory
            for song_dir in pack_dir.iterdir():
                if not song_dir.is_dir():
                    continue

                # Find audio file (.ogg, .mp3, etc.)
                for audio_ext in ['.ogg', '.mp3', '.wav']:
                    audio_files = list(song_dir.glob(f'*{audio_ext}'))
                    if audio_files:
                        audio_path = audio_files[0]
                        song_name = song_dir.name
                        results.append((audio_path, dataset, song_name))
                        break

    return results


def generate_chart(audio_path: Path, difficulty: str = 'Medium') -> dict | None:
    """
    Send an audio file to the DDC server and get back a generated chart.
    Returns parsed chart data or None on failure.
    """
    try:
        with open(audio_path, 'rb') as f:
            files = {'audio_file': (audio_path.name, f)}
            data = {
                'song_artist': '',
                'song_title': audio_path.stem,
                'diff_coarse': difficulty
            }

            response = requests.post(
                f"{DDC_SERVER_URL}/choreograph",
                files=files,
                data=data,
                timeout=300
            )

        if response.status_code != 200:
            print(f"  Error: {response.status_code} - {response.text[:100]}")
            return None

        # Parse the returned zip file
        zip_buffer = BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            for name in zf.namelist():
                if name.endswith('.sm'):
                    sm_content = zf.read(name).decode('utf-8')
                    return parse_sm_file(sm_content)

        return None

    except requests.exceptions.ConnectionError:
        print(f"  Error: Could not connect to DDC server at {DDC_SERVER_URL}")
        print("  Make sure the Docker container is running:")
        print("    docker run -it -p 8080:80 chrisdonahue/ddc:latest")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def check_server_available() -> bool:
    """Check if the DDC server is running."""
    try:
        response = requests.get(f"{DDC_SERVER_URL}/", timeout=5)
        return response.status_code == 200
    except:
        return False


def main():
    # Set up paths
    project_root = Path(__file__).parent.parent
    data_dir = project_root / 'ddc' / 'data'
    output_dir = project_root / 'generated_charts'
    output_dir.mkdir(exist_ok=True)

    # Check server
    print(f"Checking DDC server at {DDC_SERVER_URL}...")
    if not check_server_available():
        print("\nERROR: DDC server is not available!")
        print("\nTo start the server, run:")
        print("  docker run -it -p 8080:80 chrisdonahue/ddc:latest")
        print("\nThen run this script again.")
        sys.exit(1)
    print("Server is available!\n")

    # Find all audio files
    print("Finding audio files...")
    audio_files = find_audio_files(data_dir)
    print(f"Found {len(audio_files)} audio files\n")

    if not audio_files:
        print("No audio files found. Make sure the data is in ddc/data/raw/")
        sys.exit(1)

    # Difficulties to generate
    difficulties = ['Beginner', 'Easy', 'Medium', 'Hard', 'Challenge']

    # Process each file
    for audio_path, dataset, song_name in tqdm(audio_files, desc="Generating charts"):
        song_output_dir = output_dir / dataset
        song_output_dir.mkdir(exist_ok=True)

        output_file = song_output_dir / f"{song_name}_ai.json"

        # Skip if already processed
        if output_file.exists():
            continue

        result = {
            'source_audio': str(audio_path),
            'dataset': dataset,
            'song_name': song_name,
            'charts': {}
        }

        # Generate chart for each difficulty
        for diff in difficulties:
            chart_data = generate_chart(audio_path, diff)
            if chart_data and chart_data['charts']:
                result['charts'][diff] = chart_data['charts'][0]

        # Save result
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

    print(f"\nDone! Generated charts saved to {output_dir}")


if __name__ == '__main__':
    main()
