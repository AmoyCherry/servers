import subprocess
import os
import time
import json
import signal
import select
from target.base import TargetConnection


class NodeStdioTarget(TargetConnection):
    def __init__(self, config):
        self.config = config
        self.process = None

    def start(self) -> bool:
        if not os.path.exists(self.config.entry_point):
            print(f"[!] Error: Entry point not found: {self.config.entry_point}")
            return False

        # Prepare paths
        dist_dir = os.path.dirname(self.config.entry_point)
        project_root = os.path.dirname(dist_dir)
        cov_dir = os.path.join(project_root, "coverage")
        os.makedirs(cov_dir, exist_ok=True)

        cmd = ["node", "-r", self.config.hook_path, self.config.entry_point]

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=project_root,
            preexec_fn=os.setsid
        )

        # ... (Wait for [CovHook] READY logic - same as before) ...
        start_time = time.time()
        while time.time() - start_time < 5:
            line = self.process.stderr.readline()
            if "[CovHook] READY" in line:
                return True
            if not line and self.process.poll() is not None:
                return False
        return False

    # ... (Keep existing send_message, read_message, stop) ...
    def send_message(self, message: dict) -> bool:
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
            return True
        except Exception:
            return False

    def read_message(self):
        try:
            line = self.process.stdout.readline()
            if not line: return None
            return json.loads(line)
        except:
            return None

    def stop(self):
        if self.process:
            os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)

    def trigger_coverage_dump(self) -> bool:
        # ... (Keep your non-blocking implementation from the previous turn) ...
        if self.process.poll() is not None: return False
        os.killpg(os.getpgid(self.process.pid), signal.SIGUSR1)
        # Add your select.select wait loop here
        return True


class PythonStdioTarget(TargetConnection):
    """
    Runs a Python MCP server wrapped in `coverage run`.
    """

    def __init__(self, config):
        self.config = config
        self.process = None

    def start(self) -> bool:
        # We assume the entry_point is a python script or module
        # We wrap it with `coverage run` to get coverage data

        server_dir = os.path.dirname(self.config.entry_point)

        # Cmd: coverage run --branch --parallel-mode path/to/server.py
        cmd = [
            "coverage", "run",
            "--branch",
            "--parallel-mode",  # Important for concurrent processes
            self.config.entry_point
        ]

        print(f"[*] Starting Python Target: {' '.join(cmd)}")

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=server_dir,  # Python usually runs relative to script
            preexec_fn=os.setsid
        )
        return True

    def send_message(self, message: dict) -> bool:
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
            return True
        except:
            return False

    def read_message(self):
        try:
            line = self.process.stdout.readline()
            if not line: return None
            return json.loads(line)
        except:
            return None

    def trigger_coverage_dump(self) -> bool:
        """
        Python coverage is tricky. 'coverage.py' usually writes on exit.
        For runtime dumping, we might need to send a signal that the python
        script handles to call `cov.save()`.

        For now, we simulate a 'dump' by acknowledging the process is alive.
        Real implementation requires modifying the python server code to handle SIGUSR1.
        """
        if self.process.poll() is not None:
            return False
        return True

    def stop(self):
        if self.process:
            # Send SIGINT to allow coverage.py to save data gracefully
            os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)