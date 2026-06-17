from abc import ABC, abstractmethod
from dataclasses import dataclass


class ImageError(Exception):
    pass


@dataclass
class ImageCandidate:
    url: str           # direct URL of the image file to download
    alt: str           # description / alt text
    credit: str        # author / attribution (e.g. photographer name)
    source_page: str   # link back to the image's page on the stock site


class ImageProvider(ABC):
    @abstractmethod
    def search(self, query: str) -> ImageCandidate | None:
        """Return one image candidate for the query, or None if nothing found."""
