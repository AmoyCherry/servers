import json
import random
import os
from typing import List, Dict, Any
from target.base import TargetConnection


class SeedGenerator:
    def __init__(self, target: TargetConnection):
        self.target = target
        self.schemas = {
            "tools": [],
            "resources": [],
            "prompts": []
        }

    def generate(self) -> List[List[Dict[str, Any]]]:
        """
        Connects to the server, discovers capabilities, and generates
        a corpus of valid seed sequences.
        """
        print("[*] connecting to server to discover schemas...")
        if not self.target.start():
            print("[!] Failed to start target for seed generation.")
            return []

        seeds = []
        try:
            # 1. Handshake
            handshake = self._create_handshake()
            self._send_and_wait(handshake)

            # 2. Introspection (List everything)
            self._discover_capabilities()

            # 3. Generate Seeds from Schemas
            print(f"[*] Discovered {len(self.schemas['tools'])} tools, "
                  f"{len(self.schemas['resources'])} resources, "
                  f"{len(self.schemas['prompts'])} prompts.")

            # Strategy A: One seed per Tool
            for tool in self.schemas['tools']:
                seed = [handshake, self._create_tool_call(tool)]
                seeds.append(seed)

            # Strategy B: One seed per Resource
            for resource in self.schemas['resources']:
                seed = [handshake, self._create_resource_read(resource)]
                seeds.append(seed)

            # Strategy C: One seed per Prompt
            for prompt in self.schemas['prompts']:
                seed = [handshake, self._create_prompt_get(prompt)]
                seeds.append(seed)

        except Exception as e:
            print(f"[!] Error during seed generation: {e}")
        finally:
            self.target.stop()

        return seeds

    def _create_handshake(self):
        return {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "fuzzer-gen", "version": "1.0"}
            },
            "id": 1
        }

    def _send_and_wait(self, msg):
        self.target.send_message(msg)
        return self.target.read_message()

    def _discover_capabilities(self):
        # Fetch Tools
        self.target.send_message({"jsonrpc": "2.0", "method": "tools/list", "id": 2})
        resp = self.target.read_message()
        if resp and "result" in resp:
            self.schemas["tools"] = resp["result"].get("tools", [])

        # Fetch Resources
        self.target.send_message({"jsonrpc": "2.0", "method": "resources/list", "id": 3})
        resp = self.target.read_message()
        if resp and "result" in resp:
            self.schemas["resources"] = resp["result"].get("resources", [])

        # Fetch Prompts
        self.target.send_message({"jsonrpc": "2.0", "method": "prompts/list", "id": 4})
        resp = self.target.read_message()
        if resp and "result" in resp:
            self.schemas["prompts"] = resp["result"].get("prompts", [])

    def _create_tool_call(self, tool_schema):
        """Generates a valid tool call based on input schema."""
        args = {}
        schema = tool_schema.get("inputSchema", {})
        properties = schema.get("properties", {})

        for prop_name, prop_def in properties.items():
            args[prop_name] = self._generate_value_for_type(prop_name, prop_def)

        return {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": random.randint(10, 1000),
            "params": {
                "name": tool_schema["name"],
                "arguments": args
            }
        }

    def _create_resource_read(self, resource_schema):
        return {
            "jsonrpc": "2.0",
            "method": "resources/read",
            "id": random.randint(10, 1000),
            "params": {
                "uri": resource_schema["uri"]
            }
        }

    def _create_prompt_get(self, prompt_schema):
        args = {}
        for arg in prompt_schema.get("arguments", []):
            # Simple heuristic for prompt args
            args[arg["name"]] = "test_value"

        return {
            "jsonrpc": "2.0",
            "method": "prompts/get",
            "id": random.randint(10, 1000),
            "params": {
                "name": prompt_schema["name"],
                "arguments": args
            }
        }

    def _generate_value_for_type(self, name, prop_def):
        """Heuristic to generate realistic values based on type and property name."""
        p_type = prop_def.get("type", "string")

        # 1. Specific Semantic Names (Heuristics)
        if "path" in name:
            return "./README.md"
        if "uri" in name or "url" in name:
            return "https://example.com"
        if "mimeType" in name:
            return "text/plain"
        if "content" in name:
            return "Hello World Fuzzing"

        # 2. Generic Types
        if p_type == "string":
            return "test_string"
        elif p_type == "integer" or p_type == "number":
            return 123
        elif p_type == "boolean":
            return True
        elif p_type == "array":
            return []
        elif p_type == "object":
            return {}

        return "unknown"