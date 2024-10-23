import pathlib

import mock
import pytest

from tugboat import TugboatException, client_interface

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ["host_port", "container_port"], [(1, 80), (80, 1), (65535, 80), (80, 65535)]
)
def test_port_spec_ok(host_port: int, container_port: int) -> None:
    client_interface.PortSpec(host_port=host_port, container_port=container_port)


@pytest.mark.parametrize("host_port", [0, 65536])
def test_port_spec_host_port_error(host_port: int) -> None:
    with pytest.raises(ValueError, match="Invalid host port"):
        client_interface.PortSpec(host_port=host_port, container_port=80)


@pytest.mark.parametrize("container_port", [0, 65536])
def test_port_spec_container_port_error(container_port: int) -> None:
    with pytest.raises(ValueError, match="Invalid container port"):
        client_interface.PortSpec(host_port=80, container_port=container_port)


@pytest.mark.parametrize(
    ["input_path", "expected_output_path"],
    [
        (pathlib.Path("/guest1"), pathlib.PurePath("/host1")),
        (pathlib.Path("/guest1/a"), pathlib.PurePath("/host1/a")),
        (pathlib.Path("/guest1/a/b"), pathlib.PurePath("/host1/a/b")),
        (pathlib.Path("/guest2"), pathlib.PurePath("/host2")),
    ],
)
def test_get_true_host_mount_path_ok(
    input_path: pathlib.Path,
    expected_output_path: pathlib.PurePath,
) -> None:
    assert (
        # pylint: disable=protected-access
        client_interface._get_true_host_mount_path(
            {
                pathlib.PurePath("/host1"): pathlib.Path("/guest1"),
                pathlib.PurePath("/host2"): pathlib.Path("/guest2"),
            },
            input_path,
        )
        == expected_output_path
    )


def test_get_true_host_mount_path_unmapped() -> None:
    with pytest.raises(TugboatException):
        # pylint: disable=protected-access
        client_interface._get_true_host_mount_path(
            {pathlib.PurePath("/home"): pathlib.Path("/home")}, pathlib.Path("/usr")
        )


def test_get_true_host_mount_path_no_paths() -> None:
    with pytest.raises(TugboatException):
        # pylint: disable=protected-access
        client_interface._get_true_host_mount_path({}, pathlib.Path("/home"))


async def test_wait_for_container_ok() -> None:
    with mock.patch("anyio.sleep"):
        with mock.patch(
            "tugboat.client_interface._get_container_started_at_ts",
            side_effect=["0", "0", "1"],
        ):
            # pylint: disable=protected-access
            await client_interface._wait_for_container_to_start("test-id", "0")


async def test_wait_for_container_timeout() -> None:
    with mock.patch("anyio.sleep"):
        with mock.patch(
            "tugboat.client_interface._get_container_started_at_ts",
            return_value="0",
        ):
            with pytest.raises(TimeoutError):
                # pylint: disable=protected-access
                await client_interface._wait_for_container_to_start("test-id", "0")


@mock.patch("os.getgid")
@mock.patch("os.getuid")
def test_forward_user(m_getuid: mock.MagicMock, m_getgid: mock.MagicMock) -> None:
    m_getuid.return_value = "1234"
    m_getgid.return_value = "5678"
    assert client_interface.CommandSpec().forward_user().user == "1234:5678"


def test_get_docker_hostname_docker_host_unset() -> None:
    with mock.patch("os.environ", {}):
        assert client_interface.get_docker_hostname() == "localhost"


@pytest.mark.parametrize(
    "docker_host", ["file:///var/run/docker.sock", "unix:///var/run/docker.sock"]
)
def test_get_docker_hostname_docker_host_local(docker_host: str) -> None:
    with mock.patch("os.environ", {"DOCKER_HOST": docker_host}):
        assert client_interface.get_docker_hostname() == "localhost"


def test_get_docker_hostname_docker_host_remote() -> None:
    with mock.patch("os.environ", {"DOCKER_HOST": "tcp://203.0.113.1"}):
        assert client_interface.get_docker_hostname() == "203.0.113.1"


def test_get_docker_hostname_error() -> None:
    with mock.patch("os.environ", {"DOCKER_HOST": "ftp://203.0.113.1"}):
        with pytest.raises(ValueError, match="ftp"):
            client_interface.get_docker_hostname()
