import os
import json
import hashlib
import time
from typing import List, Dict, Any


class CorpusManager:
    def __init__(self, corpus_dir: str):
        self.corpus_dir = corpus_dir
        # This recursively creates fuzzer/corpus/{target_name}/
        os.makedirs(self.corpus_dir, exist_ok=True)

    def load_corpus(self) -> List[List[Dict[str, Any]]]:
        """Loads all JSON sequences from the corpus directory."""
        loaded_corpus = []
        if not os.path.exists(self.corpus_dir):
            return loaded_corpus

        print(f"[*] Loading corpus from {self.corpus_dir}...")
        for filename in os.listdir(self.corpus_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self.corpus_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        sequence = json.load(f)
                        if isinstance(sequence, list) and len(sequence) > 0:
                            loaded_corpus.append(sequence)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"[!] Warning: Failed to load seed {filename}: {e}")

        print(f"[*] Loaded {len(loaded_corpus)} seeds.")
        return loaded_corpus

    def save_seed(self, sequence: List[Dict[str, Any]]) -> str:
        """Saves a sequence to disk. Returns the filename."""
        # Create a deterministic hash of the content to prevent duplicates
        content_str = json.dumps(sequence, sort_keys=True)
        content_hash = hashlib.sha256(content_str.encode()).hexdigest()[:16]

        # Naming convention: seed_<hash>.json
        filename = f"seed_{content_hash}.json"
        filepath = os.path.join(self.corpus_dir, filename)

        # Only write if it doesn't exist (deduplication)
        if not os.path.exists(filepath):
            try:
                with open(filepath, 'w') as f:
                    f.write(content_str)
                return filename
            except IOError as e:
                print(f"[!] Error saving seed {filename}: {e}")
        return filename