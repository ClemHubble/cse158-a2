"""
Dataset loader for DDR step chart classification.
Loads human-authored charts and AI-generated charts for binary classification.
"""
import json
from pathlib import Path
from typing import Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class StepChart:
    """Represents a single step chart."""
    song_name: str
    dataset: str  # 'fraxtil' or 'itg'
    difficulty: str
    is_ai: bool
    steps: list[dict]  # List of {'time': float, 'step': str} (time in seconds)
    metadata: dict = None
    
    def __len__(self):
        return len(self.steps)
    
    @property
    def step_sequence(self) -> list[str]:
        """Get just the step patterns as a list."""
        return [s['step'] for s in self.steps]
    
    @property
    def time_sequence(self) -> list[float]:
        """Get just the times (in seconds) as a list."""
        return [s['time'] for s in self.steps]
    
    @property
    def delta_times(self) -> np.ndarray:
        """Get time differences (in seconds) between consecutive steps."""
        times = np.array(self.time_sequence)
        if len(times) < 2:
            return np.array([])
        return np.diff(times)


class DDRDataset:
    """Dataset of human and AI-generated DDR step charts."""
    
    def __init__(self, 
                 human_data_dir: Path | str,
                 ai_data_dir: Path | str,
                 datasets: list[str] = None):
        """
        Args:
            human_data_dir: Path to human_charts/ (normalized human charts)
            ai_data_dir: Path to generated_charts/ (AI charts)
            datasets: List of datasets to load ('fraxtil', 'itg'). None = all.
        """
        self.human_data_dir = Path(human_data_dir)
        self.ai_data_dir = Path(ai_data_dir)
        self.datasets = datasets or ['fraxtil', 'itg']
        
        self.charts: list[StepChart] = []
        self._load_all()
    
    def _parse_chart(self, json_path: Path, dataset: str, is_ai: bool) -> list[StepChart]:
        """
        Parse a chart JSON file (works for both human and AI).
        Both formats are now normalized to:
        {
            "song_name": "...",
            "dataset": "...",
            "charts": {
                "Difficulty": {"difficulty": "...", "steps": [...], "num_steps": N}
            }
        }
        """
        charts = []
        
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        # Get song name from data or filename
        suffix = '_ai' if is_ai else '_human'
        song_name = data.get('song_name', json_path.stem.replace(suffix, ''))
        
        for difficulty, chart_data in data.get('charts', {}).items():
            steps = chart_data.get('steps', [])
            
            if steps:
                charts.append(StepChart(
                    song_name=song_name,
                    dataset=dataset,
                    difficulty=difficulty,
                    is_ai=is_ai,
                    steps=steps,
                    metadata={'source_file': str(json_path)}
                ))
        
        return charts
    
    def _load_all(self):
        """Load all charts from both human and AI directories."""
        # Load human charts
        for dataset in self.datasets:
            dataset_dir = self.human_data_dir / dataset
            if not dataset_dir.exists():
                continue
            
            for json_path in dataset_dir.glob('*_human.json'):
                try:
                    charts = self._parse_chart(json_path, dataset, is_ai=False)
                    self.charts.extend(charts)
                except Exception as e:
                    print(f"Error loading {json_path}: {e}")
        
        # Load AI charts
        for dataset in self.datasets:
            dataset_dir = self.ai_data_dir / dataset
            if not dataset_dir.exists():
                continue
            
            for json_path in dataset_dir.glob('*_ai.json'):
                try:
                    charts = self._parse_chart(json_path, dataset, is_ai=True)
                    self.charts.extend(charts)
                except Exception as e:
                    print(f"Error loading {json_path}: {e}")
        
        print(f"Loaded {len(self.charts)} charts "
              f"({sum(1 for c in self.charts if not c.is_ai)} human, "
              f"{sum(1 for c in self.charts if c.is_ai)} AI)")
    
    def __len__(self):
        return len(self.charts)
    
    def __iter__(self) -> Iterator[StepChart]:
        return iter(self.charts)
    
    def __getitem__(self, idx) -> StepChart:
        return self.charts[idx]
    
    def get_matched_pairs(self) -> list[tuple[StepChart, StepChart]]:
        """
        Get pairs of (human, AI) charts for the same song and difficulty.
        Useful for direct comparison.
        """
        # Index human charts by (song_name, difficulty)
        human_index = {}
        for chart in self.charts:
            if not chart.is_ai:
                key = (chart.song_name, chart.difficulty)
                human_index[key] = chart
        
        pairs = []
        for chart in self.charts:
            if chart.is_ai:
                key = (chart.song_name, chart.difficulty)
                if key in human_index:
                    pairs.append((human_index[key], chart))
        
        return pairs
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert to a pandas DataFrame with basic features."""
        records = []
        for chart in self.charts:
            record = {
                'song_name': chart.song_name,
                'dataset': chart.dataset,
                'difficulty': chart.difficulty,
                'is_ai': chart.is_ai,
                'num_steps': len(chart),
            }
            
            # Add step timing features (in seconds)
            delta_times = chart.delta_times
            if len(delta_times) > 0:
                record['mean_delta_time'] = np.mean(delta_times)
                record['std_delta_time'] = np.std(delta_times)
                record['min_delta_time'] = np.min(delta_times)
                record['max_delta_time'] = np.max(delta_times)
                record['median_delta_time'] = np.median(delta_times)
            else:
                record['mean_delta_time'] = 0
                record['std_delta_time'] = 0
                record['min_delta_time'] = 0
                record['max_delta_time'] = 0
                record['median_delta_time'] = 0
            
            # Add step pattern statistics
            steps = chart.step_sequence
            if steps:
                # Count single vs multi-arrow steps
                single_arrows = sum(1 for s in steps if s.count('0') == 3)
                jumps = sum(1 for s in steps if s.count('0') == 2 and '2' not in s and '3' not in s)
                holds = sum(1 for s in steps if '2' in s or '3' in s)
                
                record['single_arrow_ratio'] = single_arrows / len(steps)
                record['jump_ratio'] = jumps / len(steps)
                record['hold_ratio'] = holds / len(steps)
                
                # Arrow distribution
                arrow_counts = [0, 0, 0, 0]  # left, down, up, right
                for step in steps:
                    for i, char in enumerate(step):
                        if char != '0':
                            arrow_counts[i] += 1
                total_arrows = sum(arrow_counts) or 1
                record['left_ratio'] = arrow_counts[0] / total_arrows
                record['down_ratio'] = arrow_counts[1] / total_arrows
                record['up_ratio'] = arrow_counts[2] / total_arrows
                record['right_ratio'] = arrow_counts[3] / total_arrows
            
            records.append(record)
        
        return pd.DataFrame(records)


def extract_ngram_features(chart: StepChart, n: int = 3) -> dict[str, int]:
    """Extract n-gram features from step sequences."""
    steps = chart.step_sequence
    if len(steps) < n:
        return {}
    
    ngrams = {}
    for i in range(len(steps) - n + 1):
        ngram = tuple(steps[i:i+n])
        ngram_str = '-'.join(ngram)
        ngrams[ngram_str] = ngrams.get(ngram_str, 0) + 1
    
    return ngrams


def extract_transition_matrix(chart: StepChart) -> np.ndarray:
    """
    Extract step transition probabilities.
    Returns a matrix where entry (i,j) is P(step j | step i).
    """
    # Map step patterns to indices
    steps = chart.step_sequence
    unique_steps = list(set(steps))
    step_to_idx = {s: i for i, s in enumerate(unique_steps)}
    n = len(unique_steps)
    
    # Count transitions
    counts = np.zeros((n, n))
    for i in range(len(steps) - 1):
        from_idx = step_to_idx[steps[i]]
        to_idx = step_to_idx[steps[i+1]]
        counts[from_idx, to_idx] += 1
    
    # Normalize to probabilities
    row_sums = counts.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1  # Avoid division by zero
    probs = counts / row_sums
    
    return probs


if __name__ == '__main__':
    # Quick test
    project_root = Path(__file__).parent.parent
    
    dataset = DDRDataset(
        human_data_dir=project_root / 'human_charts',
        ai_data_dir=project_root / 'generated_charts'
    )
    
    print(f"\nTotal charts: {len(dataset)}")
    
    # Get matched pairs
    pairs = dataset.get_matched_pairs()
    print(f"Matched pairs: {len(pairs)}")
    
    # Show example pair
    if pairs:
        human, ai = pairs[0]
        print(f"\nExample pair for '{human.song_name}' ({human.difficulty}):")
        print(f"  Human: {len(human)} steps")
        print(f"  AI: {len(ai)} steps")
    
    # Convert to DataFrame
    df = dataset.to_dataframe()
    print(f"\nDataFrame shape: {df.shape}")
    print(f"\nLabel distribution:\n{df['is_ai'].value_counts()}")

