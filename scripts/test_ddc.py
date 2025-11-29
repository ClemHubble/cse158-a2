#!/usr/bin/env python3
"""Quick test of DDC server."""
import requests
from pathlib import Path
import io
import zipfile

# Find first audio file
data_dir = Path("ddc/data/raw/fraxtil")
audio_files = list(data_dir.glob("**/*.ogg"))
print(f"Found {len(audio_files)} audio files")

if audio_files:
    audio_path = audio_files[0]
    print(f"Testing with: {audio_path}")
    
    with open(audio_path, 'rb') as f:
        files = {'audio_file': (audio_path.name, f)}
        data = {'song_artist': '', 'song_title': audio_path.stem, 'diff_coarse': 'Medium'}
        response = requests.post('http://localhost:8080/choreograph', files=files, data=data, timeout=300)
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response size: {len(response.content)} bytes")
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            print(f"Files in zip: {zf.namelist()}")
            for name in zf.namelist():
                if name.endswith('.sm'):
                    content = zf.read(name).decode('utf-8')
                    print(f"\n--- First 500 chars of {name} ---")
                    print(content[:500])
    else:
        print(f"Error: {response.text[:200]}")

