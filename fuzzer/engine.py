import random
import time
import sys
from typing import List

from target.base import TargetConnection
from cov.base import CoverageCollector
from strategies.base import MutationScheduler
from corpus.corpus_manager import CorpusManager


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
        self.corpus = self.corpus_manager.load_corpus()

    def run(self):
        print("[*] Starting fuzzing loop...")

        if not self.target.start():
            print("[!] Target failed to start initially.")
            return

        # Fallback if corpus is empty
        if not self.corpus:
            print("[!] Corpus is empty. Injecting handshake seed.")
            self.corpus.append([{
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "fuzzer"}
                },
                "id": 1
            }])

        last_dump_time = time.time()
        total_executions = 0

        try:
            while True:
                # 1. Selection
                if not self.corpus:
                    parent = []
                else:
                    parent = random.choice(self.corpus)

                # 2. Mutation
                child_sequence = self.scheduler.mutate(parent)

                # 3. Execution
                last_msg = child_sequence[-1]

                # A. Send Message
                if not self.target.send_message(last_msg):
                    print(f"\n[!] Send failed (Broken Pipe). Restarting target...")
                    self.target.stop()
                    self.target.start()
                    continue

                # --- CRITICAL FIX START ---
                # B. Read Response
                response = self.target.read_message()

                # If response is None, the server CRASHED.
                # We MUST restart and CANNOT count this as an execution.
                if response is None:
                    print(f"\n[!] Target Crashed (Empty Response). Restarting...")
                    self.target.stop()
                    self.target.start()
                    continue
                    # --- CRITICAL FIX END ---

                # Only increment if the exchange was successful
                total_executions += 1

                # 4. Feedback (Time-based: Every 10 seconds)
                current_time = time.time()
                if current_time - last_dump_time >= 10:
                    self._handle_coverage_dump(total_executions, child_sequence)
                    last_dump_time = current_time

        except KeyboardInterrupt:
            print("\n[*] Stopping Fuzzer...")
        finally:
            self.target.stop()
            print(f"[*] Final Statistics: {total_executions} executions.")

    def _handle_coverage_dump(self, executions, current_sequence):
        timestamp = time.strftime('%H:%M:%S')
        if self.target.trigger_coverage_dump():
            new_edges = self.collector.collect_new_edges()
            count_new = len(new_edges)
            total_edges = len(self.collector.global_edges)

            print(f"[*] Time: {timestamp}    Exec: {executions}    Total: {total_edges}    New: {count_new}")

            if count_new > 0:
                print(f"[+] Found {count_new} new blocks!")
                self.corpus.append(current_sequence)
                filename = self.corpus_manager.save_seed(current_sequence)
                print(f"    Saved interesting seed to: {filename}")
        else:
            print(f"[*] Time: {timestamp}    Exec: {executions}    [!] Dump Failed (Target Busy/Dead)")