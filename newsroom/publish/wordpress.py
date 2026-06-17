import logging

import httpx

from .base import PublishError, PublishOutcome, Publisher

logger = logging.getLogger(__name__)


class WordPressPublisher(Publisher):
    def publish(self, site, category, content, source_url: str, status: str = "draft") -> PublishOutcome:
        base = site.base_url.rstrip("/")
        auth = (site.auth_user, site.auth_app_password)

        tag_ids = self._ensure_tags(base, auth, list(content.tags or []))

        payload = {
            "title": content.title,
            "content": content.body_html,
            "excerpt": content.excerpt,
            "status": status,
            "tags": tag_ids,
        }
        if category:
            payload["categories"] = [category.wp_category_id]

        try:
            resp = httpx.post(
                f"{base}/wp-json/wp/v2/posts",
                auth=auth,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PublishError(
                f"WordPress API error {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except Exception as exc:
            raise PublishError(f"WordPress connection error: {exc}") from exc

        data = resp.json()
        logger.info("Published post %d at %s", data["id"], data["link"])
        return PublishOutcome(wp_post_id=data["id"], wp_url=data["link"])

    def _ensure_tags(self, base: str, auth: tuple, tag_names: list[str]) -> list[int]:
        """Get or create WordPress tags by name. Returns list of WP tag IDs."""
        tag_ids = []
        for name in tag_names:
            try:
                resp = httpx.post(
                    f"{base}/wp-json/wp/v2/tags",
                    auth=auth,
                    json={"name": name},
                    timeout=10,
                )
                if resp.status_code == 201:
                    tag_ids.append(resp.json()["id"])
                elif resp.status_code == 400:
                    data = resp.json()
                    if data.get("code") == "term_exists":
                        term_id = data.get("data", {}).get("term_id")
                        if term_id:
                            tag_ids.append(term_id)
            except Exception as exc:
                logger.warning("Could not create/get tag '%s': %s", name, exc)
        return tag_ids

    @staticmethod
    def update_status(site, wp_post_id: int, status: str) -> None:
        """Change the status of an existing post (e.g. promote draft → publish)."""
        base = site.base_url.rstrip("/")
        try:
            resp = httpx.post(
                f"{base}/wp-json/wp/v2/posts/{wp_post_id}",
                auth=(site.auth_user, site.auth_app_password),
                json={"status": status},
                timeout=30,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PublishError(
                f"WordPress API error {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except Exception as exc:
            raise PublishError(f"WordPress connection error: {exc}") from exc

    @staticmethod
    def check_connection(site) -> None:
        """Test the WordPress REST API connection. Raises on failure."""
        url = f"{site.base_url.rstrip('/')}/wp-json/wp/v2/"
        try:
            resp = httpx.get(url, auth=(site.auth_user, site.auth_app_password), timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            raise PublishError(f"Connection failed: {exc}") from exc

    @staticmethod
    def sync_categories(site) -> int:
        """Pull all categories from WordPress and upsert into WordPressCategory."""
        from newsroom.models import WordPressCategory

        base = site.base_url.rstrip("/")
        auth = (site.auth_user, site.auth_app_password)
        count = 0
        page = 1
        while True:
            resp = httpx.get(
                f"{base}/wp-json/wp/v2/categories",
                auth=auth,
                params={"per_page": 100, "page": page},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            for cat in data:
                WordPressCategory.objects.update_or_create(
                    site=site,
                    wp_category_id=cat["id"],
                    defaults={"name": cat["name"], "slug": cat["slug"]},
                )
                count += 1
            if len(data) < 100:
                break
            page += 1
        return count
