from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class DiscoveryEngine(ABC):
    @abstractmethod
    def discover(self, data_dir: Path) -> list[dict[str, Any]]:
        """Return proposed mappings in the shared Substr8 proposal shape."""
