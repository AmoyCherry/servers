# MCP Semantic Fuzzing

```text
mcp_fuzzer/
├── main.py                 # Entry point
├── engine.py               # The Fuzzing Loop
├── corpus.py               # Input management & minimization
├── strategies/             # Extensible Mutation Logic
│   ├── __init__.py
│   ├── base.py
│   ├── semantic.py         # Compliance/Violation logic
│   └── bit_level.py        # Random bit flipping
├── coverage/               # Coverage Parsing
│   ├── __init__.py
│   ├── base.py
│   └── v8.py               # Node.js V8 implementation
└── target/                 # Target Adapters
    ├── __init__.py
    ├── base.py
    └── stdio.py            # Node.js/Python Stdio handling
```