from django.core.management.base import BaseCommand

from newsroom import scheduler


class Command(BaseCommand):
    help = "Start the APScheduler process (one interval job per enabled source)"

    def handle(self, *args, **options):
        self.stdout.write("Starting scheduler. Press Ctrl+C to stop.")
        scheduler.start()
