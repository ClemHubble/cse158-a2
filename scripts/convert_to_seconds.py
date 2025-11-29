#!/usr/bin/env python3
"""
Convert all chart files to use 'time' (seconds) instead of 'beat'.

- AI charts: beat * 60 / 125 (125 BPM fixed)
- Human charts: Already have time in seconds in the source data

This script post-processes existing files in-place.
"""
import json
from pathlib import Path
from tqdm import tqdm

AI_BPM = 125.0


def convert_ai_chart(path: Path) -> bool:
    """Convert AI chart beats to seconds. Returns True if converted."""
    with open(path, 'r') as f:
        data = json.load(f)
    
    modified = False
    for difficulty, chart in data.get('charts', {}).items():
        for step in chart.get('steps', []):
            if 'beat' in step and 'time' not in step:
                step['time'] = step.pop('beat') * 60 / AI_BPM
                modified = True
    
    if modified:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    return modified


def convert_human_chart(path: Path) -> bool:
    """Verify human chart has 'time' field. Returns True if already correct."""
    with open(path, 'r') as f:
        data = json.load(f)
    
    for difficulty, chart in data.get('charts', {}).items():
        steps = chart.get('steps', [])
        if steps and 'time' not in steps[0]:
            return False  # Needs regeneration
    return True


def main():
    root = Path(__file__).parent.parent
    
    # Convert AI charts
    ai_files = list((root / 'generated_charts').glob('**/*_ai.json'))
    print(f"Processing {len(ai_files)} AI charts...")
    
    converted = 0
    for path in tqdm(ai_files, desc="AI charts"):
        if convert_ai_chart(path):
            converted += 1
    print(f"Converted {converted} AI charts to use seconds")
    
    # Check human charts
    human_files = list((root / 'human_charts').glob('**/*_human.json'))
    print(f"\nChecking {len(human_files)} human charts...")
    
    needs_regen = []
    for path in tqdm(human_files, desc="Human charts"):
        if not convert_human_chart(path):
            needs_regen.append(path)
    
    if needs_regen:
        print(f"\n{len(needs_regen)} human charts need regeneration.")
        print("Run: uv run python scripts/normalize_human_charts.py")
    else:
        print("All human charts already have 'time' field!")


if __name__ == '__main__':
    main()

