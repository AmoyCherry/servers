import argparse
import sys
import os

# Ensure we can import from local modules
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from engine import FuzzEngine
from target.stdio import NodeStdioTarget, PythonStdioTarget
from cov.v8 import V8CoverageCollector
from strategies.base import MutationScheduler
from strategies.semantic import SemanticCompliance, SemanticViolation
from corpus.corpus_manager import CorpusManager
from corpus.seed_generator import SeedGenerator
from config import TARGETS


def get_target_adapter(target_name):
    """Factory to create the right target adapter based on language."""
    if target_name not in TARGETS:
        print(f"[!] Target '{target_name}' not found in config.py")
        print(f"    Available targets: {list(TARGETS.keys())}")
        sys.exit(1)

    conf = TARGETS[target_name]

    if conf.language == "node":
        return NodeStdioTarget(conf), V8CoverageCollector(conf.coverage_file)
    elif conf.language == "python":
        # Placeholder for Python Collector
        return PythonStdioTarget(conf), V8CoverageCollector("placeholder.json")
    else:
        raise ValueError(f"Unknown language: {conf.language}")


def main():
    parser = argparse.ArgumentParser(description="MCP Fuzzer")
    parser.add_argument("--target", type=str, required=True, help="Target name (e.g., everything, filesystem, git)")
    args = parser.parse_args()

    print(f"[*] Initializing fuzzer for target: {args.target}")

    # 1. Setup Configuration
    target_adapter, coverage_collector = get_target_adapter(args.target)

    # 2. Setup Strategies
    scheduler = MutationScheduler()
    scheduler.register(SemanticCompliance(["list_files", "read_file"]), weight=80)
    scheduler.register(SemanticViolation(), weight=20)

    # 3. Setup Corpus (Target Specific!)
    # This creates paths like: fuzzer/corpus/everything/ or fuzzer/corpus/filesystem/
    target_corpus_dir = os.path.join(BASE_DIR, "corpus", args.target)

    print(f"[*] Corpus Directory: {target_corpus_dir}")
    corpus_mgr = CorpusManager(target_corpus_dir)  # <--- Passed here, Manager handles mkdir

    # 4. Auto-Seeding (Discovery)
    # If the specific target corpus is empty, generate seeds
    if not os.path.exists(target_corpus_dir) or not os.listdir(target_corpus_dir):
        print(f"[*] Corpus for '{args.target}' is empty. Discovering seeds...")

        generator = SeedGenerator(target_adapter)
        initial_seeds = generator.generate()

        if initial_seeds:
            print(f"[*] Generated {len(initial_seeds)} seeds from {args.target}.")
            for seed in initial_seeds:
                corpus_mgr.save_seed(seed)
        else:
            print("[!] Auto-discovery failed. Creating fallback handshake.")
            handshake_seed = [{
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "fuzzer"}
                },
                "id": 1
            }]
            corpus_mgr.save_seed(handshake_seed)

    # 5. Launch Engine
    engine = FuzzEngine(target_adapter, coverage_collector, scheduler, corpus_mgr)
    engine.bootstrap()
    engine.run()


#  python3 main.py --target everything
if __name__ == "__main__":
    main()