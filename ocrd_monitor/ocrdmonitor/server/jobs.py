from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeGuard

from fastapi import APIRouter, Request, Response
from fastapi.templating import Jinja2Templates

from ocrdmonitor.ocrdjob import OcrdJob
from ocrdmonitor.processstatus import ProcessStatus


@dataclass
class RunningJob:
    ocrd_job: OcrdJob
    process_status: ProcessStatus


class ProcessQuery(Protocol):
    def __call__(self, process_group: int) -> list[ProcessStatus]:
        ...


class OcrdController:
    def __init__(self, process_query: ProcessQuery, job_dir: Path) -> None:
        self._process_query = process_query
        self._job_dir = job_dir

    def get_jobs(self) -> list[OcrdJob]:
        def is_ocrd_job(j: OcrdJob | None) -> TypeGuard[OcrdJob]:
            return j is not None

        job_candidates = [
            self._try_parse(job_file.read_text())
            for job_file in self._job_dir.iterdir()
            if job_file.is_file()
        ]

        return list(filter(is_ocrd_job, job_candidates))

    def _try_parse(self, job_str: str) -> OcrdJob | None:
        try:
            return OcrdJob.from_str(job_str)
        except (ValueError, KeyError):
            return None

    def status_for(self, ocrd_job: OcrdJob) -> ProcessStatus | None:
        if ocrd_job.pid is None:
            return None

        process_statuses = self._process_query(ocrd_job.pid)
        matching_statuses = (
            status for status in process_statuses if status.pid == ocrd_job.pid
        )
        return next(matching_statuses, None)


def create_jobs(
    templates: Jinja2Templates, process_query: ProcessQuery, job_dir: Path
) -> APIRouter:
    controller = OcrdController(process_query, job_dir)

    router = APIRouter(prefix="/jobs")

    @router.get("/", name="jobs")
    def jobs(request: Request) -> Response:
        jobs = controller.get_jobs()

        running_ocrd_jobs = [job for job in jobs if job.is_running]
        completed_ocrd_jobs = [job for job in jobs if job.is_completed]

        job_status = [controller.status_for(job) for job in running_ocrd_jobs]
        running_jobs = [
            RunningJob(job, process_status)
            for job, process_status in zip(running_ocrd_jobs, job_status)
            if process_status is not None
        ]

        return templates.TemplateResponse(
            "jobs.html.j2",
            {
                "request": request,
                "running_jobs": running_jobs,
                "completed_jobs": completed_ocrd_jobs,
            },
        )

    return router