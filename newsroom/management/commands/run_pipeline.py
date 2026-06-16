from django.core.management.base import BaseCommand

from newsroom.models import Source
from newsroom import pipeline


class Command(BaseCommand):
    help = "Run the fetch pipeline for enabled sources"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-id", type=int, default=None,
            help="Run for a specific source ID only",
        )

    def handle(self, *args, **options):
        qs = Source.objects.filter(enabled=True)
        if options["source_id"]:
            qs = qs.filter(pk=options["source_id"])

        if not qs.exists():
            self.stderr.write("No enabled sources found.")
            return

        for source in qs:
            self.stdout.write(f"Fetching: {source.name} ({source.url})")
            try:
                saved, skipped = pipeline.fetch_and_store(source)
                self.stdout.write(
                    self.style.SUCCESS(f"  Done — saved: {saved}, skipped: {skipped}")
                )
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"  Error: {exc}"))
