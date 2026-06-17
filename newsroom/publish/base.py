from abc import ABC, abstractmethod
from dataclasses import dataclass


class PublishError(Exception):
    pass


@dataclass
class PublishOutcome:
    wp_post_id: int
    wp_url: str


class Publisher(ABC):
    @abstractmethod
    def publish(
        self,
        site,            # TargetSite
        category,        # WordPressCategory | None
        content,         # object with .title, .body_html, .excerpt, .tags
        source_url: str,
        status: str = "draft",
    ) -> PublishOutcome: ...
