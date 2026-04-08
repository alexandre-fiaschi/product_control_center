"""Abstract base class for all pipelines."""

from abc import ABC, abstractmethod
from typing import Any

from app.state.models import PatchEntry


class PipelineBase(ABC):
    """Base class that all pipelines must extend."""

    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def process(self, patch: PatchEntry, **kwargs: Any) -> dict:
        """Execute the pipeline for a given patch. Returns result dict."""
        ...

    @abstractmethod
    def can_process(self, patch: PatchEntry) -> bool:
        """Check if this pipeline applies to the given patch."""
        ...
