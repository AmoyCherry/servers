from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class TargetConnection(ABC):
    """Abstracts the MCP server process (Node/Python)"""

    @abstractmethod
    def start(self) -> bool:
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def send_message(self, message: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def read_message(self) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def trigger_coverage_dump(self) -> bool:
        """Signals the process to dump coverage to disk/pipe"""
        pass
