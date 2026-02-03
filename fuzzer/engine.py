import random
import time
from typing import List

from corpus.corpus_manager import CorpusManager
# Absolute imports (assuming running via python3 main.py from fuzzer/ dir)
from target.base import TargetConnection
from coverage.base import CoverageCollector
from strategies.base import MutationScheduler


class FuzzEngine:
    def __init__(self,
                 target: TargetConnection,
                 collector: CoverageCollector,
                 scheduler: MutationScheduler,
                 corpus_manager: CorpusManager):
        self.target = target
        self.collector = collector
        self.scheduler = scheduler
        self.corpus_manager = corpus_manager
        self.corpus = []
        self.start_time = time.time()

    def bootstrap(self):
        """Loads the corpus from disk."""
        self.corpus = self.corpus_manager.load_corpus()

    def run(self):
        print("[*] Starting infinite fuzzing loop (Press Ctrl+C to stop)...")

        if not self.target.start():
            print("[!] Target failed to start")
            return

        # Sanity check: We need at least one seed
        if not self.corpus:
            print("[!] Error: Empty corpus! Please ensure seeds exist in the corpus directory.")
            return

        last_dump_time = time.time()
        total_executions = 0

        try:
            while True:
                # 1. Selection
                parent = random.choice(self.corpus)

                # 2. Mutation
                child_sequence = self.scheduler.mutate(parent)

                # 3. Execution
                # Optimization: We assume persistent session state.
                # We only send the newly appended message from the sequence.
                last_msg = child_sequence[-1]

                if self.target.send_message(last_msg):
                    # Consume response to keep the pipe clear
                    self.target.read_message()
                    total_executions += 1
                else:
                    print("[!] Failed to send message (Process might be dead)")
                    break

                # 4. Feedback (Time-based: Every 10 seconds)
                current_time = time.time()
                if current_time - last_dump_time >= 10:
                    if self.target.trigger_coverage_dump():
                        new_edges = self.collector.collect_new_edges()

                        # log to console
                        log = f"\n[*] Time: {time.strftime('%D:%H:%M:%S')}    Exec: {total_executions}   Total: {len(self.collector.global_edges)}   New: {len(new_edges)}"
                        print(log)

                        # --- PERSISTENCE LOGIC ---
                        # 1. Update Memory
                        self.corpus.append(child_sequence)
                        # 2. Update Disk
                        filename = self.corpus_manager.save_seed(child_sequence)
                        print(f"    Saved interesting seed to: {filename}")
                        # -------------------------
                    else:
                        print("[!] Coverage dump failed or timed out.")

                    last_dump_time = current_time

        except KeyboardInterrupt:
            print("\n[*] Stopping Fuzzer...")
        finally:
            self.target.stop()
            print(
                f"[*] Final Statistics: {total_executions} executions, {len(self.collector.global_edges)} total blocks covered.")