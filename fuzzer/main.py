import os

from corpus.corpus_manager import CorpusManager
from engine import FuzzEngine
from target.stdio import NodeStdioTarget
from cov.v8 import V8CoverageCollector
from strategies.base import MutationScheduler
from strategies.semantic import SemanticCompliance, SemanticViolation

# Go up one level to 'servers/', then into 'src/everything/'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

# Define paths relative to the project root
HOOK_PATH = os.path.join(PROJECT_ROOT, "src/everything/cov-hook.cjs")
TARGET_JS = os.path.join(PROJECT_ROOT, "src/everything/dist/index.js")
COV_FILE = os.path.join(PROJECT_ROOT, "src/everything/coverage/runtime-dump.json")
CORPUS_DIR = os.path.join(BASE_DIR, "corpus")

# 1. Setup Strategies
scheduler = MutationScheduler()
# 80% chance to be compliant (explore deep states), 20% chance to attack
scheduler.register(SemanticCompliance(["list_files", "read_file"]), weight=80)
scheduler.register(SemanticViolation(), weight=20)

# 2. Setup Corpus Manager
corpus_mgr = CorpusManager(CORPUS_DIR)

# --- AUTO-SEEDING LOGIC ---
# If this is the first run, create the initial handshake seed
if not os.listdir(CORPUS_DIR):
    print("[*] Corpus empty. Generating initial handshake seed...")
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

# 2. Setup Components
target = NodeStdioTarget(TARGET_JS, HOOK_PATH)
collector = V8CoverageCollector(COV_FILE)

# 3. Launch
engine = FuzzEngine(target, collector, scheduler, corpus_mgr)
engine.bootstrap()
engine.run()