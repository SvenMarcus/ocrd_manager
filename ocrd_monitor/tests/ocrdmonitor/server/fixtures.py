import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from ocrdmonitor.server.app import create_app
from ocrdmonitor.server.settings import (
    OcrdBrowserSettings,
    OcrdControllerSettings,
    Settings,
)

JOB_DIR = Path(__file__).parent / "ocrd.jobs"
WORKSPACE_DIR = Path("tests") / "workspaces"


def create_settings() -> Settings:
    return Settings(
        ocrd_browser=OcrdBrowserSettings(
            workspace_dir=WORKSPACE_DIR,
            port_range=(9000, 9100),
        ),
        ocrd_controller=OcrdControllerSettings(
            job_dir=JOB_DIR,
            host="",
            user="",
        ),
    )


@pytest.fixture
def app() -> TestClient:
    return TestClient(create_app(create_settings()))