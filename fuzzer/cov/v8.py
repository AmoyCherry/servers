# src/coverage/v8.py
import json
import os
from cov.base import CoverageCollector


class V8CoverageCollector(CoverageCollector):
    def __init__(self, coverage_file_path: str):
        self.coverage_file = coverage_file_path
        self.global_edges = set()

    def collect_new_edges(self) -> set:
        if not os.path.exists(self.coverage_file):
            return set()

        try:
            with open(self.coverage_file, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return set()

        current_run_edges = set()

        # Parse the structure: Script -> Functions -> Ranges
        for script in data:
            url = script.get('url', '')

            # Filter noise (node_modules, internal node scripts)
            # We want to focus on the target server code
            if "node_modules" in url or "cov-hook" in url:
                continue

            for func in script.get('functions', []):
                for rng in func.get('ranges', []):
                    if rng['count'] > 0:
                        # Edge ID definition: "Path:StartOffset"
                        # This maps uniquely to a code block
                        edge_id = f"{url}:{rng['startOffset']}"
                        current_run_edges.add(edge_id)

        # Calculate semantic difference
        new_edges = current_run_edges - self.global_edges
        self.global_edges.update(new_edges)

        # Cleanup dump file to prepare for next run
        # (Assuming the hook appends or overwrites, usually we remove)
        try:
            os.remove(self.coverage_file)
        except OSError:
            pass

        return new_edges