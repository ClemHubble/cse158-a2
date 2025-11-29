#!/usr/bin/env python3
import json
from pathlib import Path
from tqdm import tqdm


def normalize(path: Path, group: str) -> dict | None:
    with open(path, 'r') as file:
        data = json.load(file)

    music_path = data.get('music_fp', '')
    if music_path:
        song = Path(music_path).parent.name
    else:
        song = data.get('title', path.stem)

    output = {
        'dataset': group,
        'song_name': song,
        'charts': {}
    }

    allowed = {'Beginner', 'Easy', 'Medium', 'Hard', 'Challenge'}
    seen = set()

    for chart in data.get('charts', []):
        difficulty = chart.get('difficulty_coarse', 'Unknown')

        if difficulty not in allowed:
            continue
        if difficulty in seen:
            continue
        seen.add(difficulty)

        steps = []
        for note in chart.get('notes', []):
            if len(note) >= 4:
                # note format: [[measure, subdiv, offset], beat, time_seconds, step]
                time_seconds = float(note[2])  # Use actual time in seconds
                step = note[3]
                steps.append({'time': time_seconds, 'step': step})

        if steps:
            output['charts'][difficulty] = {
                'difficulty': difficulty,
                'steps': steps,
                'num_steps': len(steps)
            }

    return output if output['charts'] else None


def main():
    root = Path(__file__).parent.parent
    human = root / 'ddc' / 'data' / 'json_filt'
    result = root / 'human_charts'

    result.mkdir(exist_ok=True)

    groups = ['fraxtil', 'itg']

    for group in groups:
        input_folder = human / group
        output_folder = result / group
        output_folder.mkdir(exist_ok=True)

        if not input_folder.exists():
            print(f"Skipping {group} - directory not found")
            continue

        files = list(input_folder.glob('**/*.json'))
        print(f"Processing {len(files)} files from {group}...")

        for path in tqdm(files, desc=group):
            chart_object = normalize(path, group)

            if chart_object:
                file_out = output_folder / \
                    f"{chart_object['song_name']}_human.json"
                with open(file_out, 'w') as write_file:
                    json.dump(chart_object, write_file, indent=2)

    total = sum(1 for _ in result.glob('**/*_human.json'))
    print(f"\nDone! Created {total} normalized human chart files in {result}")


if __name__ == '__main__':
    main()
