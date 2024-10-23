import subprocess
from typing import Any

import pytest

from .constants import BUSYBOX_IMAGE, DIND_IMAGE, UBUNTU_IMAGE


@pytest.fixture(params=["asyncio", "trio"])
def anyio_backend(request: Any) -> str:
    return request.param


# pylint: disable=unused-argument
def pytest_runtestloop() -> None:
    for image in {
        BUSYBOX_IMAGE,
        UBUNTU_IMAGE,
        DIND_IMAGE,
        # Used in a doctest in `long_running_containers.rst.inc`.
        "nginx:1.19.2",
    }:
        if not _image_present_locally(image):
            # Pre-pull images to avoid slow pulls causing test timeouts.
            _pull_image(image)


def _image_present_locally(image: str) -> bool:
    return bool(
        subprocess.run(
            ["docker", "images", "-q", image], stdout=subprocess.PIPE, check=True
        )
        .stdout.decode()
        .strip()
    )


def _pull_image(image: str) -> None:
    subprocess.run(["docker", "pull", image], check=True)
