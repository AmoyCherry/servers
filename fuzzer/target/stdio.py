import select
import subprocess
import json
import os
import signal
import time
from typing import Optional

from target.base import TargetConnection


class NodeStdioTarget(TargetConnection):
    def __init__(self, entry_point: str, hook_path: str):
        self.entry_point = entry_point
        self.hook_path = hook_path
        self.process = None

    def start(self) -> bool:
        if not os.path.exists(self.entry_point):
            print(f"[!] Error: Entry point not found: {self.entry_point}")
            return False

            # --- FIX START ---
            # 1. Determine the Project Root (assuming entry is inside /dist/)
            # Current: .../servers/src/everything/dist/index.js
            # Target CWD: .../servers/src/everything/
        dist_dir = os.path.dirname(self.entry_point)
        project_root = os.path.dirname(dist_dir)

        # 2. Ensure the 'coverage' directory exists in the Project Root
        # This prevents the ENOENT error from Node.js
        cov_dir = os.path.join(project_root, "coverage")
        os.makedirs(cov_dir, exist_ok=True)
        # --- FIX END ---

        cmd = ["node", "-r", self.hook_path, self.entry_point]
        print(f"[*] Running command: {' '.join(cmd)}")
        print(f"[*] CWD: {project_root}")  # Debug info

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=project_root,  # <--- CHANGED: Run from project root, not dist
            preexec_fn=os.setsid
        )

        # Wait for Hook Ready
        start_time = time.time()
        while time.time() - start_time < 5:
            # Non-blocking read is safer, but for debug let's just peek
            line = self.process.stderr.readline()

            if line:
                print(f"[NODE STDERR]: {line.strip()}")  # PRINT EVERYTHING FROM NODE

            if "[CovHook] READY" in line:
                return True

            # check if process died
            if self.process.poll() is not None:
                print(f"[!] Node process died with code {self.process.returncode}")
                # Read remaining stderr to see why it died
                print(self.process.stderr.read())
                return False

        print("[!] Timeout waiting for [CovHook] READY")
        return False

    def send_message(self, message: dict) -> bool:
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
            return True
        except (BrokenPipeError, AttributeError):
            return False

    def read_message(self) -> Optional[dict]:
        try:
            line = self.process.stdout.readline()
            if not line: return None
            return json.loads(line)
        except:
            return None

    def trigger_coverage_dump(self) -> bool:
        """Sends SIGUSR1 and waits for DUMP_COMPLETE with a timeout."""
        if self.process.poll() is not None:
            return False

        # 1. Send the signal
        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGUSR1)
        except ProcessLookupError:
            return False

        # 2. Wait for confirmation (Timeout after 2 seconds)
        start_wait = time.time()
        timeout = 2.0

        while time.time() - start_wait < timeout:
            # Check if stderr has data waiting (non-blocking check)
            # select parameters: (read_list, write_list, error_list, timeout)
            ready_to_read, _, _ = select.select([self.process.stderr], [], [], 0.1)

            if ready_to_read:
                line = self.process.stderr.readline()

                # If process closed stderr, it likely died
                if not line:
                    return False

                # Check for success
                if "DUMP_COMPLETE" in line:
                    return True

                # Debug: Print unexpected output (e.g., "Debugger listening...")
                print(f"[NODE LOG]: {line.strip()}")

            # Check if process died while waiting
            if self.process.poll() is not None:
                return False

        print(f"[!] Timeout: Node process is alive but didn't return DUMP_COMPLETE.")
        return False

    def stop(self):
        if self.process:
            os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)