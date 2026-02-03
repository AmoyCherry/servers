import os

# Define the root of the 'servers' repo relative to this config file
# Assuming structure:
#   servers/
#     fuzzer/config.py
#     src/everything/
#     src/filesystem/
#     ...
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class ToolConfig:
    def __init__(self, name, language, entry_point, hook_path=None, coverage_file=None):
        self.name = name
        self.language = language  # "node" or "python"
        self.entry_point = os.path.join(REPO_ROOT, entry_point)

        # Coverage defaults
        if language == "node":
            self.hook_path = os.path.join(REPO_ROOT, hook_path or "src/everything/cov-hook.cjs")
            # Node usually dumps to the CWD of the server
            self.coverage_file = coverage_file or "coverage/runtime-dump.json"
        elif language == "python":
            # Python usually runs via 'uv' or direct python execution
            self.hook_path = None  # Python coverage handled via CLI wrapper
            self.coverage_file = coverage_file or ".coverage"


# Registry of the 7 common targets
TARGETS = {
    # --- TypeScript/Node.js Targets ---
    "everything": ToolConfig(
        name="everything",
        language="node",
        entry_point="src/everything/dist/index.js",
        coverage_file="src/everything/coverage/runtime-dump.json"
    ),
    "filesystem": ToolConfig(
        name="filesystem",
        language="node",
        entry_point="src/filesystem/dist/index.js",
        coverage_file="src/filesystem/coverage/runtime-dump.json"
    ),
    "memory": ToolConfig(
        name="memory",
        language="node",
        entry_point="src/memory/dist/index.js",
        coverage_file="src/memory/coverage/runtime-dump.json"
    ),
    "fetch": ToolConfig(
        name="fetch",
        language="node",
        entry_point="src/fetch/dist/index.js",
        coverage_file="src/fetch/coverage/runtime-dump.json"
    ),
    "sequentialthinking": ToolConfig(  # Assuming puppeteer is the 5th JS tool
        name="sequentialthinking",
        language="node",
        entry_point="src/sequentialthinking/dist/index.js",
        coverage_file="src/sequentialthinking/coverage/runtime-dump.json"
    ),

    # --- Python Targets (Examples) ---
    "git": ToolConfig(
        name="git",
        language="python",
        # For python, entry point is often the module name or path
        entry_point="src/git/src/mcp_server_git/server.py"
    ),
    "time": ToolConfig(
        name="time",
        language="python",
        entry_point="src/time/src/mcp_server_time/server.py"
    ),
}