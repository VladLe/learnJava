from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FetchedItem:
    guid: str
    url: str
    title: str
    summary: str | None
    published_at: datetime | None


class SourceFetcher(ABC):
    @abstractmethod
    def fetch(self, source) -> list[FetchedItem]: ...
