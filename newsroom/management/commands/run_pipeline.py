from django.core.management.base import BaseCommand

from newsroom.models import Source
from newsroom import pipeline


class Command(BaseCommand):
    help = "Run the pipeline (fetch / extract / rewrite) for enabled sources"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-id", type=int, default=None,
            help="Run for a specific source ID only",
        )
        parser.add_argument(
            "--step",
            choices=["fetch", "extract", "rewrite", "publish", "all"],
            default="all",
            help="Which pipeline step to run (default: all)",
        )

    def handle(self, *args, **options):
        qs = Source.objects.filter(enabled=True)
        if options["source_id"]:
            qs = qs.filter(pk=options["source_id"])

        if not qs.exists():
            self.stderr.write("No enabled sources found.")
            return

        step = options["step"]

        for source in qs:
            self.stdout.write(f"\nSource: {source.name}")

            if step in ("fetch", "all"):
                try:
                    saved, skipped = pipeline.fetch_and_store(source)
                    self.stdout.write(
                        self.style.SUCCESS(f"  Fetch   — saved: {saved}, skipped: {skipped}")
                    )
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"  Fetch error: {exc}"))
                    continue

            if step in ("extract", "all"):
                try:
                    extracted, failed = pipeline.extract_articles(source)
                    self.stdout.write(
                        self.style.SUCCESS(f"  Extract — done: {extracted}, failed: {failed}")
                    )
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"  Extract error: {exc}"))

            if step in ("rewrite", "all"):
                try:
                    rewritten, failed = pipeline.rewrite_articles(source)
                    self.stdout.write(
                        self.style.SUCCESS(f"  Rewrite — done: {rewritten}, failed: {failed}")
                    )
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"  Rewrite error: {exc}"))

            if step in ("publish", "all"):
                try:
                    published, failed = pipeline.publish_articles(source)
                    self.stdout.write(
                        self.style.SUCCESS(f"  Publish — done: {published}, failed: {failed}")
                    )
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"  Publish error: {exc}"))
