import contextlib
import datetime
import json
import logging
import os
import pathlib
import subprocess
import tempfile
from signal import SIGKILL
from typing import Any, Dict, Iterator, Set, Union

import _pytest.capture
import _pytest.logging
import anyio
import mock
import pytest
import requests

import tugboat
from tugboat import _compat
from tugboat.exceptions import TugboatException

from .constants import BUSYBOX_IMAGE, DIND_IMAGE, NGINX_IMAGE, UBUNTU_IMAGE

BASE_TEMP_DIR = pathlib.Path(os.environ.get("TUGBOAT_TEST_TEMP_DIR", "/tmp"))

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("assert_no_leaked_containers")]

_log = logging.getLogger(__name__)


@pytest.fixture
def anyio_backend() -> str:
    # These tests are relatively slow to run, so default to running on just one
    # backend.
    return "asyncio"


@pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])
async def test_simple_run() -> None:
    result = await tugboat.run(
        tugboat.ContainerSpec(BUSYBOX_IMAGE)
        .set_args(["echo", "hello world"])
        .set_stdout(tugboat.PIPE)
    )
    assert result.returncode == 0
    assert result.stdout == "hello world\n"


def test_simple_run_sync() -> None:
    result = tugboat.run_sync(
        tugboat.ContainerSpec(BUSYBOX_IMAGE)
        .set_args(["echo", "hello world"])
        .set_stdout(tugboat.PIPE)
    )
    assert result.returncode == 0
    assert result.stdout == "hello world\n"


@pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])
@pytest.mark.parametrize(
    "fail_function",
    [
        pytest.param("tugboat.client_interface.create", id="create"),
        pytest.param("tugboat.client_interface.start", id="start"),
        pytest.param("tugboat.client_interface.remove", id="remove"),
    ],
)
async def test_simple_run_docker_error(fail_function: str) -> None:
    """This test checks only that no containers are leaked."""
    with mock.patch(fail_function, side_effect=Exception):
        with pytest.raises(Exception):
            await tugboat.run(tugboat.ContainerSpec(BUSYBOX_IMAGE))


@pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])
@mock.patch("tugboat.client_interface._wait_for_container_to_start")
async def test_simple_run_start_timeout(m_wait_for_start: mock.MagicMock) -> None:
    """This test checks only that no containers are leaked."""
    m_wait_for_start.side_effect = TimeoutError
    with pytest.raises(TugboatException):
        await tugboat.run(tugboat.ContainerSpec(BUSYBOX_IMAGE))


@pytest.mark.parametrize(
    "contents",
    [pytest.param("hello world", id="str"), pytest.param(b"hello world", id="bytes")],
)
async def test_add_file(contents: Union[bytes, str]) -> None:
    assert (
        (
            await tugboat.run(
                tugboat.ContainerSpec(BUSYBOX_IMAGE)
                .add_file(pathlib.PurePath("/home/test/file.txt"), contents)
                .set_args(["cat", "/home/test/file.txt"])
                .set_stdout(tugboat.PIPE)
            )
        ).stdout
    ) == "hello world"


async def test_set_working_directory() -> None:
    assert (
        await tugboat.run(
            tugboat.ContainerSpec(BUSYBOX_IMAGE)
            .set_working_directory(pathlib.PurePath("/home/docker"))
            .set_args(["pwd"])
            .set_stdout(tugboat.PIPE)
        )
    ).stdout == "/home/docker\n"


async def test_add_environment_variable() -> None:
    assert (
        await tugboat.run(
            tugboat.ContainerSpec(BUSYBOX_IMAGE)
            .add_environment_variable("hello", "world")
            .set_args(["printenv", "hello"])
            .set_stdout(tugboat.PIPE)
        )
    ).stdout == "world\n"


async def test_forward_environment_variable() -> None:
    with set_env_var("hello", "world"):
        assert (
            await tugboat.run(
                tugboat.ContainerSpec(BUSYBOX_IMAGE)
                .forward_environment_variable("hello")
                .set_args(["printenv", "hello"])
                .set_stdout(tugboat.PIPE)
            )
        ).stdout == "world\n"


async def test_add_extra_docker_args() -> None:
    assert (
        await tugboat.run(
            tugboat.ContainerSpec(BUSYBOX_IMAGE)
            .add_extra_docker_args(["-e", "hello=world"])
            .set_args(["printenv", "hello"])
            .set_stdout(tugboat.PIPE)
        )
    ).stdout == "world\n"


async def test_set_log_name(caplog: _pytest.logging.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    await tugboat.run(tugboat.ContainerSpec(BUSYBOX_IMAGE).set_log_name("hello world"))
    assert "hello world" in caplog.text


async def test_default_stdout(capfd: _pytest.capture.CaptureFixture[str]) -> None:
    await tugboat.run(
        tugboat.ContainerSpec(BUSYBOX_IMAGE).set_args(["echo", "hello world"])
    )
    assert capfd.readouterr().out == "hello world\n"


async def test_specified_stdout_path(
    capfd: _pytest.capture.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    stdout = tmp_path / "stdout"
    await tugboat.run(
        tugboat.ContainerSpec(BUSYBOX_IMAGE)
        .set_stdout(stdout)
        .set_args(["echo", "hello world"])
    )

    with open(stdout, encoding="utf-8") as f:
        assert f.read() == "hello world\n"

    # With container stdout set, no output should be produced to the Python
    # process stdout.
    assert capfd.readouterr().out == ""


async def test_specified_stdout_textio(
    capfd: _pytest.capture.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    stdout = tmp_path / "stdout"
    with open(stdout, "w", encoding="utf-8") as f:
        await tugboat.run(
            tugboat.ContainerSpec(BUSYBOX_IMAGE)
            .set_stdout(f)
            .set_args(["echo", "hello world"])
        )

    with open(stdout, encoding="utf-8") as f:
        assert f.read() == "hello world\n"
    assert capfd.readouterr().out == ""


async def test_specified_stdout_pipe(
    capfd: _pytest.capture.CaptureFixture[str],
) -> None:
    result = await tugboat.run(
        tugboat.ContainerSpec(BUSYBOX_IMAGE)
        .set_stdout(tugboat.PIPE)
        .set_args(["echo", "hello world"])
    )
    assert result.stdout == "hello world\n"
    assert capfd.readouterr().out == ""


async def test_suppress_stdout(capfd: _pytest.capture.CaptureFixture[str]) -> None:
    await tugboat.run(
        tugboat.ContainerSpec(BUSYBOX_IMAGE)
        .suppress_stdout()
        .set_args(["echo", "hello world"])
    )
    assert capfd.readouterr().out == ""


async def test_default_stderr(capfd: _pytest.capture.CaptureFixture[str]) -> None:
    await tugboat.run(
        tugboat.ContainerSpec(BUSYBOX_IMAGE).set_args(["ls", "--not-a-flag"])
    )
    assert "--not-a-flag" in capfd.readouterr().err


async def test_specified_stderr_path(
    capfd: _pytest.capture.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    stderr = tmp_path / "stderr"
    await tugboat.run(
        tugboat.ContainerSpec(BUSYBOX_IMAGE)
        .set_stderr(stderr)
        .set_args(["ls", "--not-a-flag"])
    )

    with open(stderr, encoding="utf-8") as f:
        assert "--not-a-flag" in f.read()

    # With container stderr set, no output should be produced to the Python
    # process stderr.
    assert capfd.readouterr().err == ""


async def test_specified_stderr_textio(
    capfd: _pytest.capture.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    stderr = tmp_path / "stderr"
    with open(stderr, "w", encoding="utf-8") as f:
        await tugboat.run(
            tugboat.ContainerSpec(BUSYBOX_IMAGE)
            .set_stderr(f)
            .set_args(["ls", "--not-a-flag"])
        )

    with open(stderr, encoding="utf-8") as f:
        assert "--not-a-flag" in f.read()
    assert capfd.readouterr().err == ""


async def test_specified_stderr_pipe(
    capfd: _pytest.capture.CaptureFixture[str],
) -> None:
    result = await tugboat.run(
        tugboat.ContainerSpec(BUSYBOX_IMAGE)
        .set_stderr(tugboat.PIPE)
        .set_args(["ls", "--not-a-flag"])
    )
    assert "--not-a-flag" in result.stderr
    assert capfd.readouterr().err == ""


async def test_suppress_stderr(capfd: _pytest.capture.CaptureFixture[str]) -> None:
    await tugboat.run(
        tugboat.ContainerSpec(BUSYBOX_IMAGE)
        .suppress_stderr()
        .set_args(["ls", "--not-a-flag"])
    )
    assert capfd.readouterr().err == ""


async def test_exec_ok() -> None:
    async with tugboat.ContainerFactory().start(
        tugboat.ContainerSpec(BUSYBOX_IMAGE).run_indefinitely()
    ) as container:
        result = await container.exec(
            tugboat.ExecSpec(["printenv", "hello"])
            .add_environment_variable("hello", "world")
            .set_stdout(tugboat.PIPE)
            .set_stderr(tugboat.PIPE)
        )
    assert result.stdout == "world\n"
    assert result.stderr == ""


async def test_dind() -> None:
    async with tugboat.ContainerFactory().start(
        tugboat.ContainerSpec(DIND_IMAGE)
        .add_extra_docker_args(["--privileged"])
        .add_bind_mount(
            tugboat.BindMountSpec(
                pathlib.Path("/var/lib/docker/overlay2"),
                pathlib.PurePath("/var/lib/docker/overlay2"),
            )
        )
        .add_bind_mount(
            tugboat.BindMountSpec(
                pathlib.Path("/var/lib/docker/image"),
                pathlib.PurePath("/var/lib/docker/image"),
            )
        )
    ) as dind_container:
        # Wait for docker service to be running
        await dind_container.exec(
            tugboat.ExecSpec(
                ["sh", "-c", "while ! docker ps > /dev/null 2>&1; do sleep 1; done"]
            )
        )

        async with tugboat.ContainerFactory(
            docker_client_wrapper=lambda cmd: [
                "docker",
                "exec",
                "-i",
                dind_container.id,
                *cmd,
            ]
        ).start(tugboat.ContainerSpec(BUSYBOX_IMAGE).run_indefinitely()) as container:
            _log.info("Testing exec() with Docker-in-Docker")
            result = await container.exec(
                tugboat.ExecSpec(["printenv", "hello"])
                .add_environment_variable("hello", "world")
                .set_stdout(tugboat.PIPE)
                .set_stderr(tugboat.PIPE)
            )
            assert result.stdout == "world\n"
            assert result.stderr == ""

            _log.info("Testing add_file() / extract_file() with Docker-in-Docker")
            file_path = pathlib.PurePath("/home/test/file.txt")
            with pytest.raises(TugboatException):
                await container.extract_file(file_path)
            await container.add_file(file_path, b"hello world")
            assert (await container.extract_file(file_path)) == b"hello world"

        _log.info("Testing pid and kill() with Docker-in-Docker")
        async with tugboat.ContainerFactory(
            docker_client_wrapper=lambda cmd: [
                "docker",
                "exec",
                "-i",
                dind_container.id,
                *cmd,
            ]
        ).start(tugboat.ContainerSpec(BUSYBOX_IMAGE).run_indefinitely()) as container:
            await container.pid
            await container.kill()

        _log.info("Testing force remove if standard remove() throws an Exception")
        with mock.patch("tugboat.client_interface.remove", side_effect=Exception):
            with pytest.raises(Exception):
                await tugboat.ContainerFactory(
                    docker_client_wrapper=lambda cmd: [
                        "docker",
                        "exec",
                        "-i",
                        dind_container.id,
                        *cmd,
                    ]
                ).run(tugboat.ContainerSpec(BUSYBOX_IMAGE))


async def test_exec_err() -> None:
    async with tugboat.ContainerFactory().start(
        tugboat.ContainerSpec(BUSYBOX_IMAGE).run_indefinitely()
    ) as container:
        with pytest.raises(subprocess.CalledProcessError, match="not_set_env_var"):
            await container.exec(tugboat.ExecSpec(["printenv", "not_set_env_var"]))


async def test_exec_err_ignored() -> None:
    async with tugboat.ContainerFactory().start(
        tugboat.ContainerSpec(BUSYBOX_IMAGE).run_indefinitely()
    ) as container:
        await container.exec(
            tugboat.ExecSpec(["printenv", "not_set_env_var"]).check_exit_code(False)
        )


@pytest.mark.parametrize(
    "contents",
    [pytest.param("hello world", id="str"), pytest.param(b"hello world", id="bytes")],
)
async def test_add_file_to_running_container(contents: Union[bytes, str]) -> None:
    async with tugboat.ContainerFactory().start(
        tugboat.ContainerSpec(BUSYBOX_IMAGE).run_indefinitely()
    ) as container:

        async def cat() -> str:
            # If the file is not present `cat` will error - but it won't
            # produce any stdout.
            return (
                await container.exec(
                    tugboat.ExecSpec(["cat", "/home/test/file.txt"])
                    .set_stdout(tugboat.PIPE)
                    .check_exit_code(False)
                )
            ).stdout

        assert (await cat()) == ""
        await container.add_file(pathlib.PurePath("/home/test/file.txt"), contents)
        assert (await cat()) == "hello world"


@pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])
@pytest.mark.parametrize(
    "fail_function",
    [
        pytest.param("tugboat.client_interface.create", id="create"),
        pytest.param("tugboat.client_interface.start", id="start"),
        pytest.param("tugboat.client_interface.wait", id="wait"),
        pytest.param("tugboat.client_interface.remove", id="remove"),
    ],
)
async def test_start_docker_error(fail_function: str) -> None:
    """
    Test encountering an error when running various Docker commands.

    This test checks only that no containers are leaked.
    """
    with mock.patch(fail_function, side_effect=Exception):
        # Multiple tasks may raise exceptions when the event loop is cancelled.
        # These are grouped by anyio into a single exception that is not derived
        # from `Exception`.
        with pytest.raises(BaseException):
            async with tugboat.ContainerFactory().start(
                tugboat.ContainerSpec(BUSYBOX_IMAGE).run_indefinitely()
            ):
                await anyio.sleep(30)


@pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])
async def test_start_external_error() -> None:
    """
    Test handling of an error raised outside tugboat within its context manager.

    This test checks only that no containers are leaked.
    """
    with pytest.raises(Exception):
        async with tugboat.ContainerFactory().start(
            tugboat.ContainerSpec(BUSYBOX_IMAGE).run_indefinitely()
        ):
            raise Exception


async def test_set_user() -> None:
    async with tugboat.ContainerFactory().start(
        tugboat.ContainerSpec(BUSYBOX_IMAGE).set_user("1234:5678").run_indefinitely()
    ) as container:
        assert (
            await container.exec(tugboat.ExecSpec(["id", "-u"], stdout=tugboat.PIPE))
        ).stdout == "1234\n"
        assert (
            await container.exec(tugboat.ExecSpec(["id", "-g"], stdout=tugboat.PIPE))
        ).stdout == "5678\n"


@pytest.mark.parametrize(
    ["network", "expected_network_name"],
    [
        pytest.param(tugboat.Network.NONE, "none", id="none"),
        pytest.param(tugboat.Network.HOST, "host", id="host"),
    ],
)
async def test_set_network(
    network: tugboat.Network, expected_network_name: str
) -> None:
    async with tugboat.ContainerFactory().start(
        tugboat.ContainerSpec(BUSYBOX_IMAGE).set_network(network).run_indefinitely()
    ) as container:
        assert list(inspect(container.id)["NetworkSettings"]["Networks"].keys()) == [
            expected_network_name
        ]


async def test_publish_port() -> None:
    docker_hostname = tugboat.get_docker_hostname()
    host_port = 8080
    async with tugboat.ContainerFactory().start(
        tugboat.ContainerSpec(NGINX_IMAGE).publish_port(
            tugboat.PortSpec(host_port=host_port, container_port=80)
        )
    ):
        await retry_get(f"http://{docker_hostname}:{host_port}")


async def retry_get(url: str) -> None:
    attempts = 0
    while True:
        attempts += 1
        try:
            requests.get(url).raise_for_status()
            return
        except requests.RequestException as e:
            if attempts == 10:
                raise
            _log.info(f"GET failed: {e}")
        await anyio.sleep(1)


async def test_add_label() -> None:
    async with tugboat.ContainerFactory().start(
        tugboat.ContainerSpec(BUSYBOX_IMAGE)
        .add_label("key", "value")
        .add_label("label")
        .run_indefinitely()
    ) as container:
        assert inspect(container.id)["Config"]["Labels"] == {
            "key": "value",
            "label": "",
        }


@pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])
async def test_unexpected_exit() -> None:
    with pytest.raises(tugboat.ContainerException) as exc_info:
        async with tugboat.ContainerFactory().start(
            tugboat.ContainerSpec(BUSYBOX_IMAGE)
        ):
            await anyio.sleep(30)
    assert "0" in str(exc_info.value)


@pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])
async def test_unexpected_exit_code() -> None:
    with pytest.raises(tugboat.ContainerException) as exc_info:
        async with tugboat.ContainerFactory().start(
            # The busybox image doesn't include bash, so use ubuntu instead.
            tugboat.ContainerSpec(UBUNTU_IMAGE).set_args(
                ["/bin/bash", "-c", 'trap "exit 13" SIGTERM; sleep infinity & wait']
            )
        ):
            await anyio.sleep(30)
    assert "13" in str(exc_info.value)


@pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])
async def test_kill() -> None:
    async with tugboat.ContainerFactory().start(
        tugboat.ContainerSpec(BUSYBOX_IMAGE).run_indefinitely()
    ) as container:
        await container.kill()


@pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])
async def test_stop_with_timeout() -> None:
    async with tugboat.ContainerFactory().start(
        # This container will ignore a SIGTERM and only exit when it is killed.
        tugboat.ContainerSpec(BUSYBOX_IMAGE)
        .set_entrypoint("sleep")
        .set_args(["infinity"])
    ) as container:
        start = datetime.datetime.now()
        async with anyio.create_task_group() as task_group:
            await _compat.start_soon(
                task_group,
                lambda: container.stop(timeout=datetime.timedelta(seconds=3)),
            )
            assert (
                await container.wait({128 + SIGKILL.value})
            ).returncode == 128 + SIGKILL.value

        end = datetime.datetime.now()
        assert (end - start).total_seconds() > 3


async def test_bind_mount() -> None:
    with tempfile.TemporaryDirectory(dir=BASE_TEMP_DIR) as tempdir:
        with open(f"{tempdir}/file.txt", "w", encoding="utf-8") as f:
            f.write("hello world")
        assert (
            await tugboat.ContainerFactory({BASE_TEMP_DIR: BASE_TEMP_DIR}).run(
                tugboat.ContainerSpec(BUSYBOX_IMAGE)
                .set_args(["cat", "/home/docker/file.txt"])
                .set_stdout(tugboat.PIPE)
                .add_bind_mount(
                    tugboat.BindMountSpec(
                        pathlib.Path(tempdir),
                        pathlib.PurePath("/home/docker"),
                        read_only=True,
                    )
                )
            )
        ).stdout == "hello world"


async def test_already_removed() -> None:
    async with tugboat.ContainerFactory().start(
        tugboat.ContainerSpec(BUSYBOX_IMAGE).run_indefinitely()
    ) as container:
        await container.kill()
        await container.wait()
        await container.remove()


@pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])
async def test_remove_error() -> None:
    with mock.patch("tugboat.client_interface.remove", side_effect=Exception):
        with pytest.raises(Exception):
            await tugboat.run(tugboat.ContainerSpec(BUSYBOX_IMAGE))


@pytest.fixture
def assert_no_leaked_containers() -> Iterator[None]:
    created_container_ids: Set[str] = set()

    def register_container_id(container_id: str) -> str:
        created_container_ids.add(container_id)
        return container_id

    with mock.patch(
        "tugboat.client_interface._register_container_id", register_container_id
    ):
        try:
            yield
        finally:

            existing_container_ids = set(
                subprocess.run(
                    ["docker", "ps", "-aq", "--no-trunc"],
                    check=True,
                    stdout=subprocess.PIPE,
                )
                .stdout.decode()
                .strip()
                .splitlines()
            )
            _log.debug("Existing container ids: %s", existing_container_ids)
            _log.debug("Created container ids: %s", created_container_ids)

            assert not (
                created_container_ids & existing_container_ids
            ), "Container(s) leaked!"


@contextlib.contextmanager
def set_env_var(name: str, value: str) -> Iterator[None]:
    prev_value = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if prev_value is None:
            del os.environ[name]
        else:
            os.environ[name] = prev_value


def inspect(container_id: str) -> Dict[str, Any]:
    return json.loads(
        subprocess.run(
            ["docker", "inspect", container_id],
            check=True,
            stdout=subprocess.PIPE,
            encoding="utf-8",
        ).stdout.strip()
    )[0]
