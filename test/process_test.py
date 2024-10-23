import logging
import subprocess

import mock
import pytest

from tugboat import exceptions, process

pytestmark = pytest.mark.anyio


async def test_run_process_stderr(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(exceptions.DockerException):
            await process.run(["ls", "--not-a-flag"])
    assert len([m for m in caplog.messages if "--not-a-flag" in m]) > 0


@mock.patch("anyio.run_process")
async def test_run_process_error(m_run_process: mock.MagicMock) -> None:
    m_run_process.side_effect = subprocess.CalledProcessError(
        1, ["test", "cmd"], output=b"", stderr=b""
    )
    with pytest.raises(exceptions.DockerException) as exc_info:
        await process.run(["test", "cmd"])
    assert exc_info.value.returncode == 1
    assert exc_info.value.cmd == ["test", "cmd"]


def test_run_process_sync_stderr(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(exceptions.DockerException):
            process.run_sync(["ls", "--not-a-flag"])
    assert len([m for m in caplog.messages if "--not-a-flag" in m]) > 0


@mock.patch("subprocess.run")
def test_run_process_sync_error(m_run_process: mock.MagicMock) -> None:
    m_run_process.side_effect = subprocess.CalledProcessError(1, ["test", "cmd"])
    with pytest.raises(exceptions.DockerException) as exc_info:
        process.run_sync(["test", "cmd"])
    assert exc_info.value.returncode == 1
    assert exc_info.value.cmd == ["test", "cmd"]
