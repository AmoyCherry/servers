from typing import List, Dict

from strategies.base import MutationStrategy
import copy
import random


class SemanticCompliance(MutationStrategy):
    """Generates valid MCP tool calls to explore application state"""

    def __init__(self, known_tools: List[str]):
        self.tools = known_tools

    def mutate(self, sequence: List[Dict]) -> List[Dict]:
        new_seq = copy.deepcopy(sequence)
        tool = random.choice(self.tools)

        # In a real scenario, we would use a schema fuzzer here
        # to generate valid params for the specific tool.
        new_seq.append({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": len(new_seq) + 1,
            "params": {
                "name": tool,
                "arguments": {}
            }
        })
        return new_seq


class SemanticViolation(MutationStrategy):
    """Generates invalid types or forbidden paths"""

    def mutate(self, sequence: List[Dict]) -> List[Dict]:
        new_seq = copy.deepcopy(sequence)

        # Example: Inject a type confusion payload
        new_seq.append({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": len(new_seq) + 1,
            "params": {
                "name": "filesystem/write",
                "arguments": {
                    "path": "/etc/passwd",  # Forbidden path injection
                    "content": 0xFFFFFFFF  # Type confusion (int instead of str)
                }
            }
        })
        return new_seq