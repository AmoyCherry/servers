import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class MutationStrategy(ABC):
    @abstractmethod
    def mutate(self, sequence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pass


class MutationScheduler:
    def __init__(self):
        self.strategies = []
        self.weights = []

    def register(self, strategy: MutationStrategy, weight: int):
        self.strategies.append(strategy)
        self.weights.append(weight)

    def mutate(self, sequence: List[Dict]) -> List[Dict]:
        strategy = random.choices(self.strategies, weights=self.weights, k=1)[0]
        return strategy.mutate(sequence)