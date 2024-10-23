"""Tests for interacting with an already running container."""

import pathlib
from typing import AsyncGenerator, Union

import pytest

import tugboat
from tugboat import Container, process

from .constants import BUSYBOX_IMAGE

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    # These tests are relatively slow to run, so default to running on just one
    # backend.
    return "asyncio"


# Rename this fixture to avoid pylint complaints about the tests which use this
# fixture shadowing its name.
@pytest.fixture(name="non_tugboat_container_id")
async def fixture_non_tugboat_container_id() -> AsyncGenerator[str, None]:
    """
    Launch a container without using tugboat.

    This is useful for making sure that tugboat's ability to manage existing
    containers doesn't rely on something specific about the way tugboat launches
    containers.

    We set the container up to run indefinitely - it will be killed at the end
    of each test if it isn't dead already, and then removed.
    """
    container_id = await process.run(
        ["docker", "run", "-d", BUSYBOX_IMAGE, "sleep", "infinity"]
    )
    yield container_id

    # Kill it (if it's not already dead) and remove it
    await process.run(["docker", "rm", "-f", container_id])


def to_bytes(contents: Union[str, bytes]) -> bytes:
    if isinstance(contents, str):
        return contents.encode()
    return contents


async def test_pid(non_tugboat_container_id: str) -> None:
    container = Container.from_container_id(non_tugboat_container_id)
    pid = await container.pid
    # PID must be a positive integer and cannot clash with the init
    # process's PID (1), but maximum PID is platform dependent so don't
    # assert an upper bound.
    assert pid > 1


@pytest.mark.parametrize(
    "contents",
    [pytest.param("hello world", id="str"), pytest.param(b"hello world", id="bytes")],
)
async def test_add_file(
    contents: Union[bytes, str], non_tugboat_container_id: str
) -> None:
    container = Container.from_container_id(non_tugboat_container_id)
    await container.add_file(pathlib.PurePath("/home/test/file.txt"), contents)

    result = await container.exec(
        tugboat.ExecSpec(["cat", "/home/test/file.txt"])
        .set_stdout(tugboat.PIPE)
        .set_stderr(tugboat.PIPE)
    )
    assert result.stdout == "hello world"
    assert result.stderr == ""


@pytest.mark.parametrize(
    "contents",
    [pytest.param("hello world", id="str"), pytest.param(b"hello world", id="bytes")],
)
async def test_extract_file(
    contents: Union[bytes, str], non_tugboat_container_id: str
) -> None:
    container = Container.from_container_id(non_tugboat_container_id)
    await container.add_file(pathlib.PurePath("/home/test/file.txt"), contents)

    # Extract the new file from the container and compare the contents as
    # bytes.
    extracted_bytes = await container.extract_file(
        pathlib.PurePath("/home/test/file.txt")
    )
    assert extracted_bytes == to_bytes(contents)


async def test_kill_wait(non_tugboat_container_id: str) -> None:
    """
    Test calling wait() on a Container object created from a container ID.

    Create a Container object to manage an existing container. When the existing
    container is kiled (using the container object produced by the
    non_tugboat_container_id fixture rather than the tugboat Container), the Container
    object should be able to wait() on the container (which will find that it's already
    exited). It won't have captured anything in stdout or stderr because these are only
    available to Container objects created before starting the container.
    """
    container = Container.from_container_id(non_tugboat_container_id)
    await process.run(["docker", "kill", non_tugboat_container_id])
    result = await container.wait()
    assert result.stdout is None
    assert result.stderr is None
