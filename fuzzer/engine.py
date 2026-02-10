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
        self._request_id = 0
        self._initialized = False

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def bootstrap(self):
        self.corpus = self.corpus_manager.load_corpus()

    def run(self):
        print("[*] Starting fuzzing loop...")

        if not self.target.start():
            print("[!] Target failed to start initially.")
            return

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
                # Execute full sequence, not just last message
                for msg in child_sequence:
                    method = msg.get("method")

                    # Skip initialize if we've already done it this session
                    if method == "initialize" and self._initialized:
                        continue

                    # Force unique id for every message sent
                    msg = dict(msg)
                    msg["id"] = self._next_id()

                    if not self.target.send_message(msg):
                        print(f"\n[!] Send failed (Broken Pipe). Restarting target...")
                        self.target.stop()
                        self.target.start()
                        self._initialized = False
                        break

                    response = None
                    for _ in range(3):  # retry up to 3 times
                        response = self.target.read_message(expected_id=msg["id"], timeout_sec=2.0)
                        if response is not None:
                            break

                    if response is None:
                        # print(f"\n[!] Target Unresponsive (Empty Response/Timeout). Restarting...")
                        # self.target.stop()
                        # self.target.start()
                        # self._initialized = False
                        break

                    if method == "initialize":
                        self._initialized = True

                else:
                    # Only count if the whole sequence ran successfully
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