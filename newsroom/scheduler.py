import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.conf import settings
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution

from .models import Source

logger = logging.getLogger(__name__)


def run_source_job(source_id: int) -> None:
    """APScheduler entry point: run the pipeline for one source by id.

    Looked up fresh each run so the scheduler always uses current settings.
    """
    from . import pipeline

    try:
        source = Source.objects.get(pk=source_id, enabled=True)
    except Source.DoesNotExist:
        logger.info("Source %d disabled or missing — skipping job", source_id)
        return
    pipeline.run_source(source)


def register_jobs(scheduler) -> None:
    """Register one interval job per enabled source."""
    for source in Source.objects.filter(enabled=True):
        scheduler.add_job(
            run_source_job,
            trigger=IntervalTrigger(minutes=source.fetch_interval_minutes),
            args=[source.id],
            id=f"source-{source.id}",
            max_instances=1,
            replace_existing=True,
            jobstore="default",
        )
        logger.info(
            "Scheduled source '%s' every %d min", source.name, source.fetch_interval_minutes
        )


def delete_old_job_executions(max_age: int = 7 * 24 * 60 * 60) -> None:
    """Remove DjangoJobExecution rows older than max_age seconds."""
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


def start() -> None:
    """Build a blocking scheduler, register jobs and run until interrupted."""
    scheduler = BlockingScheduler(timezone=settings.TIME_ZONE)
    scheduler.add_jobstore(DjangoJobStore(), "default")

    register_jobs(scheduler)

    scheduler.add_job(
        delete_old_job_executions,
        trigger=IntervalTrigger(days=1),
        id="delete_old_job_executions",
        max_instances=1,
        replace_existing=True,
    )

    logger.info("Starting scheduler…")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping scheduler…")
        scheduler.shutdown()
