from __future__ import annotations

import copy
import json
import random
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from strategies.base import MutationStrategy

READ_KEYWORDS = (
    "read", "get", "list", "search", "show", "status", "diff", "log", "open", "fetch", "tree", "info"
)
WRITE_KEYWORDS = (
    "write", "edit", "create", "add", "delete", "remove", "move", "update", "set", "commit", "checkout", "reset"
)
SEQUENCE_DEPENDENCY_RULES = (
    (("commit",), ("add", "stage")),
    (("relation",), ("entity", "node", "create")),
    (("checkout",), ("create", "branch")),
    (("delete", "update"), ("create", "add", "write")),
)
SENSITIVE_PATHS = (
    "../../../etc/passwd",
    "../../../../../../etc/shadow",
    "../../.ssh/authorized_keys",
    "../.env",
    "/etc/passwd",
)


def _tokenize(name: str) -> List[str]:
    return [token for token in re.split(r"[^a-zA-Z0-9]+", (name or "").lower()) if token]


def _is_tool_call(msg: Dict[str, Any]) -> bool:
    return msg.get("method") == "tools/call" and isinstance(msg.get("params"), dict)


def _is_read_tool(name: str) -> bool:
    tokens = _tokenize(name)
    return any(keyword in tokens for keyword in READ_KEYWORDS)


def _is_write_tool(name: str) -> bool:
    tokens = _tokenize(name)
    return any(keyword in tokens for keyword in WRITE_KEYWORDS)


def _next_msg_id(sequence: List[Dict[str, Any]]) -> int:
    return len(sequence) + 1


def _build_initialize(msg_id: int) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "semantic-fuzzer", "version": "1.0"}
        },
        "id": msg_id
    }


def _build_tool_call(msg_id: int, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": msg_id,
        "params": {
            "name": name,
            "arguments": arguments
        }
    }


def _shared_domain_score(a: str, b: str) -> int:
    a_tokens = set(_tokenize(a))
    b_tokens = set(_tokenize(b))
    a_tokens -= set(READ_KEYWORDS + WRITE_KEYWORDS)
    b_tokens -= set(READ_KEYWORDS + WRITE_KEYWORDS)
    return len(a_tokens & b_tokens)


class SemanticCompliance(MutationStrategy):
    """
    Deterministic compliant mutation strategy.
    No randomness is used for selecting the next compliant call.
    """

    def __init__(self, known_tools: Optional[List[str]] = None):
        self.tools = known_tools or []

        self._tool_order: List[str] = []
        self._tool_templates: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._template_hashes: Dict[str, set[str]] = defaultdict(set)
        self._template_cursor: Dict[str, int] = defaultdict(int)

        self._resource_reads: List[str] = []
        self._prompt_gets: List[Dict[str, Any]] = []

        self._phase = 0
        self._tool_cursor = 0
        self._resource_cursor = 0
        self._prompt_cursor = 0

        self._path_counter = 0
        self._entity_counter = 0
        self._last_path = "./README.md"
        self._last_entity = "Entity_0"

        for tool in self.tools:
            self._remember_tool_template(tool, {})

    def mutate(self, sequence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self._ingest_sequence(sequence)
        new_seq = copy.deepcopy(sequence)

        if not any(msg.get("method") == "initialize" for msg in new_seq):
            new_seq.append(_build_initialize(_next_msg_id(new_seq)))
            return new_seq

        phase = self._phase % 4
        self._phase += 1

        # Phase 3 prefers protocol-compliant non-tool actions if we have them.
        if phase == 3:
            protocol_msg = self._next_protocol_message(new_seq)
            if protocol_msg is not None:
                new_seq.append(protocol_msg)
                return new_seq

        pool = self._select_tool_pool(phase)
        if not pool:
            fallback_name = self.tools[0] if self.tools else "echo"
            new_seq.append(_build_tool_call(_next_msg_id(new_seq), fallback_name, {"message": "semantic-compliance"}))
            return new_seq

        tool_name = pool[self._tool_cursor % len(pool)]
        self._tool_cursor += 1
        args = self._build_compliant_args(tool_name, phase)
        new_seq.append(_build_tool_call(_next_msg_id(new_seq), tool_name, args))
        return new_seq

    def _ingest_sequence(self, sequence: List[Dict[str, Any]]) -> None:
        for msg in sequence:
            method = msg.get("method")
            params = msg.get("params", {})
            if method == "tools/call" and isinstance(params, dict):
                tool_name = params.get("name")
                if not tool_name:
                    continue
                arguments = params.get("arguments", {})
                if not isinstance(arguments, dict):
                    arguments = {}
                self._remember_tool_template(tool_name, arguments)
            elif method == "resources/read" and isinstance(params, dict):
                uri = params.get("uri")
                if isinstance(uri, str) and uri not in self._resource_reads:
                    self._resource_reads.append(uri)
            elif method == "prompts/get" and isinstance(params, dict):
                name = params.get("name")
                if not isinstance(name, str):
                    continue
                arguments = params.get("arguments", {})
                if not isinstance(arguments, dict):
                    arguments = {}
                prompt_call = {"name": name, "arguments": arguments}
                if prompt_call not in self._prompt_gets:
                    self._prompt_gets.append(prompt_call)

    def _remember_tool_template(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        if tool_name not in self._tool_templates:
            self._tool_order.append(tool_name)
        key = json.dumps(arguments, sort_keys=True)
        if key in self._template_hashes[tool_name]:
            return
        self._template_hashes[tool_name].add(key)
        self._tool_templates[tool_name].append(copy.deepcopy(arguments))

    def _select_tool_pool(self, phase: int) -> List[str]:
        all_tools = [name for name in self._tool_order if name]
        if not all_tools:
            return []

        producers = [name for name in all_tools if _is_write_tool(name)]
        consumers = [name for name in all_tools if _is_read_tool(name)]

        if phase in (0, 1):
            return producers or all_tools
        if phase == 2:
            return consumers or all_tools
        return all_tools

    def _next_protocol_message(self, sequence: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if self._resource_reads:
            uri = self._resource_reads[self._resource_cursor % len(self._resource_reads)]
            self._resource_cursor += 1
            return {
                "jsonrpc": "2.0",
                "method": "resources/read",
                "id": _next_msg_id(sequence),
                "params": {"uri": uri},
            }
        if self._prompt_gets:
            prompt = self._prompt_gets[self._prompt_cursor % len(self._prompt_gets)]
            self._prompt_cursor += 1
            return {
                "jsonrpc": "2.0",
                "method": "prompts/get",
                "id": _next_msg_id(sequence),
                "params": {
                    "name": prompt["name"],
                    "arguments": copy.deepcopy(prompt.get("arguments", {})),
                },
            }
        return None

    def _build_compliant_args(self, tool_name: str, phase: int) -> Dict[str, Any]:
        templates = self._tool_templates.get(tool_name, [{}])
        if not templates:
            templates = [{}]

        idx = self._template_cursor[tool_name] % len(templates)
        self._template_cursor[tool_name] += 1
        args = copy.deepcopy(templates[idx])

        if not isinstance(args, dict):
            args = {}

        normalized = {}
        for key, value in args.items():
            normalized[key] = self._normalize_value(tool_name, key, value, phase)

        # Backfill common required fields when schema seeds were empty.
        lowered_name = tool_name.lower()
        if "path" in lowered_name and "path" not in normalized:
            normalized["path"] = self._next_path(read_like=_is_read_tool(tool_name))
        if "repo" in lowered_name and "repo_path" not in normalized:
            normalized["repo_path"] = "."
        if "timezone" in lowered_name:
            normalized.setdefault("timezone", "UTC")
            normalized.setdefault("source_timezone", "UTC")
            normalized.setdefault("target_timezone", "America/New_York")

        self._capture_artifacts(tool_name, normalized)
        return normalized

    def _normalize_value(self, tool_name: str, key: str, value: Any, phase: int) -> Any:
        key_lower = key.lower()

        if isinstance(value, dict):
            return {k: self._normalize_value(tool_name, k, v, phase) for k, v in value.items()}

        if isinstance(value, list):
            if not value:
                return self._fill_empty_list_for_key(key_lower)
            return [self._normalize_value(tool_name, key, item, phase) for item in value]

        if isinstance(value, bool):
            if key_lower == "nextthoughtneeded":
                return phase != 3
            if key_lower in ("isrevision", "needsmorethoughts"):
                return False
            return value

        if isinstance(value, int):
            if key_lower in ("thoughtnumber",):
                return 1 + (self._phase % 3)
            if key_lower in ("totalthoughts",):
                return 3
            if key_lower in ("duration", "steps", "count", "max_count", "max_length"):
                return max(1, min(value, 32))
            if key_lower in ("start_index", "head", "tail"):
                return 0 if key_lower == "start_index" else 10
            return value

        if isinstance(value, float):
            return float(int(value))

        if isinstance(value, str):
            if "repo_path" in key_lower:
                return "."
            if key_lower in ("revision", "target"):
                return "HEAD"
            if "branch" in key_lower:
                return "main"
            if "timezone" in key_lower:
                return "UTC" if "target" not in key_lower else "America/New_York"
            if key_lower == "time":
                return "12:34"
            if "url" in key_lower or "uri" in key_lower:
                return "https://example.com"
            if "query" in key_lower:
                return "example query"
            if "pattern" in key_lower:
                return "*.md"
            if "source" in key_lower and "path" in key_lower:
                return self._last_path
            if "destination" in key_lower:
                return self._next_path(read_like=False)
            if "path" in key_lower:
                return self._next_path(read_like=_is_read_tool(tool_name))
            if key_lower in ("name", "entityname"):
                return self._next_entity_name()
            if key_lower in ("from", "to"):
                return self._next_entity_name()
            if key_lower == "relationtype":
                return "related_to"
            if key_lower == "entitytype":
                return "person"
            if "message" in key_lower:
                return "compliance message"
            if "content" in key_lower:
                return "compliance content"
            if "thought" == key_lower:
                return "Step-by-step analysis."
            if value in ("", "test_string", "unknown"):
                return f"value_{self._phase}"
            return value

        return value

    def _fill_empty_list_for_key(self, key_lower: str) -> List[Any]:
        if key_lower == "paths":
            return [self._next_path(read_like=True)]
        if key_lower == "files":
            return ["README.md"]
        if key_lower in ("names", "entitynames"):
            return [self._next_entity_name()]
        if key_lower == "entities":
            name = self._next_entity_name()
            return [{"name": name, "entityType": "person", "observations": ["observed by semantic compliance"]}]
        if key_lower == "relations":
            return [{"from": self._next_entity_name(), "to": self._next_entity_name(), "relationType": "related_to"}]
        if key_lower == "observations":
            return [{"entityName": self._next_entity_name(), "contents": ["compliance observation"]}]
        if key_lower == "deletions":
            return [{"entityName": self._next_entity_name(), "observations": ["compliance observation"]}]
        if key_lower == "excludepatterns":
            return []
        return []

    def _next_path(self, read_like: bool) -> str:
        if read_like:
            return self._last_path
        self._path_counter += 1
        self._last_path = f"./fuzz-state/file-{self._path_counter}.txt"
        return self._last_path

    def _next_entity_name(self) -> str:
        self._entity_counter += 1
        self._last_entity = f"Entity_{self._entity_counter}"
        return self._last_entity

    def _capture_artifacts(self, _tool_name: str, args: Dict[str, Any]) -> None:
        for key, value in args.items():
            if not isinstance(value, str):
                continue
            lowered = key.lower()
            if "path" in lowered and value:
                self._last_path = value
            if lowered in ("name", "entityname", "from", "to") and value:
                self._last_entity = value


class SemanticViolation(MutationStrategy):
    """
    Semantic violation strategy with three sub-strategies:
    1) Logic Contradiction (high focus)
    2) Sequence Violation (high focus)
    3) Hallucination Injection (low probability)
    """

    def __init__(self, hallucination_weight: float = 0.08):
        self.hallucination_weight = max(0.0, min(hallucination_weight, 0.3))
        self.logic_weight = (1.0 - self.hallucination_weight) / 2.0
        self.sequence_weight = (1.0 - self.hallucination_weight) / 2.0

        self._tool_order: List[str] = []
        self._tool_templates: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._template_hashes: Dict[str, set[str]] = defaultdict(set)
        self._template_cursor: Dict[str, int] = defaultdict(int)
        self._violation_counter = 0
        self._path_payload_cursor = 0

    def mutate(self, sequence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self._ingest_sequence(sequence)
        new_seq = copy.deepcopy(sequence)

        builders = [
            ("logic", self.logic_weight, self._logic_contradiction_payload),
            ("sequence", self.sequence_weight, self._sequence_violation_payload),
            ("hallucination", self.hallucination_weight, self._hallucination_injection_payload),
        ]
        chosen_name = random.choices(
            [name for name, _, _ in builders],
            weights=[weight for _, weight, _ in builders],
            k=1
        )[0]

        chosen_builder = next(builder for name, _, builder in builders if name == chosen_name)
        fallback_builders = [builder for name, _, builder in builders if name != chosen_name]

        payload_calls = chosen_builder(sequence)
        if not payload_calls:
            for builder in fallback_builders:
                payload_calls = builder(sequence)
                if payload_calls:
                    break
        if not payload_calls:
            payload_calls = [self._legacy_fallback_payload()]

        for payload in payload_calls:
            msg = copy.deepcopy(payload)
            msg["id"] = _next_msg_id(new_seq)
            new_seq.append(msg)
        return new_seq

    def _ingest_sequence(self, sequence: List[Dict[str, Any]]) -> None:
        for msg in sequence:
            if not _is_tool_call(msg):
                continue
            params = msg.get("params", {})
            tool_name = params.get("name")
            if not isinstance(tool_name, str):
                continue
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            self._remember_tool_template(tool_name, arguments)

    def _remember_tool_template(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        if tool_name not in self._tool_templates:
            self._tool_order.append(tool_name)
        key = json.dumps(arguments, sort_keys=True)
        if key in self._template_hashes[tool_name]:
            return
        self._template_hashes[tool_name].add(key)
        self._tool_templates[tool_name].append(copy.deepcopy(arguments))

    def _pick_template(self, tool_name: str) -> Dict[str, Any]:
        templates = self._tool_templates.get(tool_name, [{}])
        if not templates:
            return {}
        idx = self._template_cursor[tool_name] % len(templates)
        self._template_cursor[tool_name] += 1
        template = templates[idx]
        return copy.deepcopy(template if isinstance(template, dict) else {})

    def _tool_has_path_like_args(self, tool_name: str) -> bool:
        for template in self._tool_templates.get(tool_name, []):
            if not isinstance(template, dict):
                continue
            for key in template.keys():
                lowered = key.lower()
                if "path" in lowered or lowered in ("source", "destination", "repo_path"):
                    return True
        return False

    def _logic_contradiction_payload(self, sequence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        read_calls = []
        for msg in sequence:
            if not _is_tool_call(msg):
                continue
            name = msg.get("params", {}).get("name", "")
            if isinstance(name, str) and _is_read_tool(name):
                read_calls.append(msg)

        write_tools = [tool for tool in self._tool_order if _is_write_tool(tool)]
        if not write_tools:
            write_tools = ["filesystem/write"]

        chosen_read = read_calls[-1] if read_calls else None
        chosen_write = write_tools[0]

        if chosen_read:
            read_name = chosen_read.get("params", {}).get("name", "")
            best_score = -1
            for candidate in write_tools:
                score = _shared_domain_score(read_name, candidate)
                if self._tool_has_path_like_args(candidate):
                    score += 1
                if score > best_score:
                    best_score = score
                    chosen_write = candidate
        else:
            for candidate in write_tools:
                if self._tool_has_path_like_args(candidate):
                    chosen_write = candidate
                    break

        read_payload = None
        if chosen_read:
            read_name = chosen_read["params"]["name"]
            read_args = copy.deepcopy(chosen_read["params"].get("arguments", {}))
            if "path" in read_args:
                read_args["path"] = "./README.md"
            read_payload = _build_tool_call(0, read_name, read_args)

        write_args = self._pick_template(chosen_write)
        write_args = self._apply_logic_contradiction(chosen_write, write_args)
        write_payload = _build_tool_call(0, chosen_write, write_args)

        if read_payload is not None:
            return [read_payload, write_payload]
        return [write_payload]

    def _sequence_violation_payload(self, _sequence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self._violation_counter += 1
        tools = [name for name in self._tool_order if name]
        if not tools:
            return []

        # Targeted case: memory server relation creation without entities.
        if "create_relations" in self._tool_templates:
            args = self._pick_template("create_relations")
            args["relations"] = [{
                "from": f"ghost_from_{self._violation_counter}",
                "to": f"ghost_to_{self._violation_counter}",
                "relationType": "depends_on"
            }]
            return [_build_tool_call(0, "create_relations", args)]

        # Targeted case: git commit without add/stage.
        if "git_commit" in self._tool_templates:
            args = self._pick_template("git_commit")
            args.setdefault("repo_path", ".")
            args["message"] = f"sequence-violation-{self._violation_counter}"
            return [_build_tool_call(0, "git_commit", args)]

        # Generic dependency inversion: call dependent tool before prerequisite.
        for dependent_name in tools:
            prerequisite = self._find_prerequisite(dependent_name, tools)
            if prerequisite is None:
                continue

            dependent_args = self._inject_missing_dependency_args(dependent_name, self._pick_template(dependent_name))
            prerequisite_args = self._pick_template(prerequisite)
            return [
                _build_tool_call(0, dependent_name, dependent_args),
                _build_tool_call(0, prerequisite, prerequisite_args),
            ]

        # Fallback: dependent-style call with non-existent identifiers.
        dependent_candidates = [
            name for name in tools
            if any(token in _tokenize(name) for token in ("commit", "delete", "update", "checkout", "open", "read", "show"))
        ]
        if dependent_candidates:
            tool_name = dependent_candidates[0]
            args = self._inject_missing_dependency_args(tool_name, self._pick_template(tool_name))
            return [_build_tool_call(0, tool_name, args)]
        return []

    def _find_prerequisite(self, dependent_name: str, all_tools: List[str]) -> Optional[str]:
        dependent_tokens = set(_tokenize(dependent_name))
        for dependent_markers, prerequisite_markers in SEQUENCE_DEPENDENCY_RULES:
            if not any(marker in dependent_tokens for marker in dependent_markers):
                continue
            for candidate in all_tools:
                candidate_tokens = set(_tokenize(candidate))
                if any(marker in candidate_tokens for marker in prerequisite_markers):
                    return candidate
        return None

    def _inject_missing_dependency_args(self, _tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if not args:
            return {"id": f"missing_state_{self._violation_counter}"}

        mutated = copy.deepcopy(args)
        for key, value in list(mutated.items()):
            key_lower = key.lower()
            if key_lower in ("name", "entityname", "branch_name", "revision", "target"):
                mutated[key] = f"missing_{key}_{self._violation_counter}"
            elif "path" in key_lower and isinstance(value, str):
                mutated[key] = f"./nonexistent-{self._violation_counter}.txt"
            elif isinstance(value, list):
                if key_lower == "relations":
                    mutated[key] = [{
                        "from": f"ghost_from_{self._violation_counter}",
                        "to": f"ghost_to_{self._violation_counter}",
                        "relationType": "depends_on",
                    }]
                elif key_lower in ("names", "entitynames", "files"):
                    mutated[key] = [f"missing_{self._violation_counter}"]
                else:
                    mutated[key] = []
        return mutated

    def _hallucination_injection_payload(self, _sequence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tools = [name for name in self._tool_order if name]
        if not tools:
            return []

        tool_name = tools[self._violation_counter % len(tools)]
        self._violation_counter += 1
        args = self._pick_template(tool_name)

        # Omit a likely required field when available.
        preferred_required = (
            "path", "repo_path", "url", "timezone", "source_timezone", "target_timezone",
            "message", "entities", "relations", "name"
        )
        for key in preferred_required:
            if key in args:
                args.pop(key)
                break
        else:
            if args:
                first_key = next(iter(args))
                args.pop(first_key)

        # Add hallucinated fields.
        args["force"] = True
        args["ignore_permissions"] = True
        args["uid"] = 0
        args["unsafe_mode"] = "root"
        args["__proto__"] = {"polluted": True}

        # Type confusion: overwrite one existing argument with wrong type.
        for key, value in list(args.items()):
            if key in ("force", "ignore_permissions", "uid", "unsafe_mode", "__proto__"):
                continue
            if isinstance(value, str):
                args[key] = {"unexpected": "object"}
            elif isinstance(value, bool):
                args[key] = "true"
            elif isinstance(value, (int, float)):
                args[key] = "NaN"
            elif isinstance(value, list):
                args[key] = "not-an-array"
            elif isinstance(value, dict):
                args[key] = ["not-an-object"]
            break

        return [_build_tool_call(0, tool_name, args)]

    def _apply_logic_contradiction(self, _tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        payload_path = SENSITIVE_PATHS[self._path_payload_cursor % len(SENSITIVE_PATHS)]
        self._path_payload_cursor += 1

        if not args:
            return {
                "path": payload_path,
                "content": "semantic contradiction payload",
            }

        mutated = copy.deepcopy(args)
        for key, value in list(mutated.items()):
            key_lower = key.lower()

            if isinstance(value, str):
                if "path" in key_lower or "source" in key_lower or "destination" in key_lower:
                    mutated[key] = payload_path
                elif "uri" in key_lower or "url" in key_lower:
                    mutated[key] = "file:///etc/passwd"
                elif key_lower in ("revision", "target"):
                    mutated[key] = "../../../../etc/passwd"
                elif "message" in key_lower:
                    mutated[key] = "unsafe write request"
                elif "content" in key_lower:
                    mutated[key] = "attempting sensitive overwrite"
            elif isinstance(value, bool):
                mutated[key] = True
            elif isinstance(value, int):
                mutated[key] = 2147483647
            elif isinstance(value, float):
                mutated[key] = 1e18
            elif isinstance(value, list):
                if key_lower in ("paths", "files"):
                    mutated[key] = [payload_path]
                elif key_lower == "entities":
                    mutated[key] = [{
                        "name": payload_path,
                        "entityType": "system_file",
                        "observations": ["contradiction injected"],
                    }]
                elif key_lower == "relations":
                    mutated[key] = [{
                        "from": payload_path,
                        "to": "../../../../etc/shadow",
                        "relationType": "writes_to",
                    }]
                elif key_lower in ("names", "entitynames"):
                    mutated[key] = [payload_path]
            elif isinstance(value, dict):
                mutated[key] = {"elevated": True}

        if "path" not in mutated and any(mark in _tool_name.lower() for mark in ("write", "edit", "move", "file")):
            mutated["path"] = payload_path
        if "content" not in mutated and any(mark in _tool_name.lower() for mark in ("write", "edit")):
            mutated["content"] = "semantic contradiction payload"

        return mutated

    def _legacy_fallback_payload(self) -> Dict[str, Any]:
        return _build_tool_call(
            0,
            "filesystem/write",
            {
                "path": "/etc/passwd",
                "content": 0xFFFFFFFF,
            },
        )
