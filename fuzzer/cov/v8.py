import json
import os
from cov.base import CoverageCollector


class V8CoverageCollector(CoverageCollector):
    def __init__(self, coverage_file_path: str):
        self.coverage_file = coverage_file_path
        self.global_edges = set()

    def collect_new_edges(self) -> set:
        if not os.path.exists(self.coverage_file):
            print(f"[!] Coverage file not found: {self.coverage_file}")
            return set()

        try:
            with open(self.coverage_file, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return set()

        current_run_edges = set()
        seen_scripts = []

        # Parse the structure: Script -> Functions -> Ranges
        for script in data:
            url = script.get('url', '')

            # Debug: Track what we see to diagnose "Total: 0"
            if "node_modules" not in url and "cov-hook" not in url:
                seen_scripts.append(url)

            # Filter noise (node_modules, internal node scripts)
            if "node_modules" in url or "cov-hook" in url:
                continue

            for func in script.get('functions', []):
                for rng in func.get('ranges', []):
                    if rng['count'] > 0:
                        edge_id = f"{url}:{rng['startOffset']}"
                        current_run_edges.add(edge_id)

        # If we found nothing, print what we DID see (for debugging)
        if not current_run_edges and seen_scripts:
            print(f"[DEBUG] Saw scripts but found 0 blocks: {seen_scripts}")
        elif not current_run_edges and not seen_scripts:
            # If this prints, it means index.js is MISSING from the dump
            print(f"[DEBUG] V8 Dump contained only node_modules/hooks. Target missing?")

        # Calculate semantic difference
        new_edges = current_run_edges - self.global_edges
        self.global_edges.update(new_edges)

        try:
            os.remove(self.coverage_file)
        except OSError:
            pass

        return new_edges