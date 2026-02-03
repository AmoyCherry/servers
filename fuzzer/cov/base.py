from abc import ABC, abstractmethod


class CoverageCollector(ABC):
    """Abstracts parsing coverage data from different runtimes"""

    @abstractmethod
    def collect_new_edges(self) -> set:
        """Returns a set of unique edge IDs found in the last run"""
        pass