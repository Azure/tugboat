import enum
import io
import logging
import os
import pathlib
import subprocess
import sys
import tarfile
import urllib.parse
from datetime import timedelta
from signal import Signals
from typing import (
    AsyncIterator,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    TextIO,
    TypeVar,
    Union,
)

import anyio
import async_generator
import attr

from . import _compat, exceptions, process, streams

log = logging.getLogger(__name__)

Self = TypeVar("Self", bound="CommandSpec")


@attr.s(auto_attribs=True)
class CommandSpec:
    """Common Docker command options between ``docker create`` and ``docker exec``."""

    #: Container user.
    user: Optional[str] = attr.ib(default=None, kw_only=True)

    #: Container working directory.
    working_directory: Optional[pathlib.PurePath] = attr.ib(default=None, kw_only=True)

    #: Container environment variables.
    environment: Dict[str, Optional[str]] = attr.ib(factory=dict, kw_only=True)

    #: Extra arguments to pass to Docker.
    extra_docker_args: List[str] = attr.ib(factory=list, kw_only=True)

    #: Stream to which command stdout is written. See
    #: :any:`tugboat.ContainerSpec.stdout`
    stdout: streams.OutStream = attr.ib(factory=lambda: sys.stdout, kw_only=True)

    #: Stream to which command stderr is written. See
    #: :any:`tugboat.ContainerSpec.stderr`
    stderr: streams.OutStream = attr.ib(factory=lambda: sys.stderr, kw_only=True)

    def set_user(self: Self, user: str) -> Self:
        """Set the container user."""
        self.user = user
        return self

    def forward_user(self: Self) -> Self:
        """Set the container user to match the UID/GID of the current user."""
        return self.set_user(f"{os.getuid()}:{os.getgid()}")

    def set_working_directory(self: Self, working_directory: pathlib.PurePath) -> Self:
        """Set the container working directory."""
        self.working_directory = working_directory
        return self

    def add_environment_variable(self: Self, name: str, value: str) -> Self:
        """Add an environment variable to the container."""
        self.environment[name] = value
        return self

    def forward_environment_variable(self: Self, name: str) -> Self:
        """Set an environment variable in the container to its value in the current environment."""
        self.environment[name] = None
        return self

    def add_extra_docker_args(self: Self, args: Sequence[str]) -> Self:
        """Add extra arguments to pass to Docker."""
        self.extra_docker_args += args
        return self

    def set_stdout(self: Self, stdout: streams.OutStream) -> Self:
        """Set the file or file descriptor to which container stdout is written."""
        self.stdout = stdout
        return self

    def set_stderr(self: Self, stderr: streams.OutStream) -> Self:
        """Set the file to which container stderr is written."""
        self.stderr = stderr
        return self

    def suppress_stdout(self: Self) -> Self:
        """
        Suppress container stdout.

        Container stdout is redirected to `/dev/null`.
        """
        return self.set_stdout(pathlib.Path("/dev/null"))

    def suppress_stderr(self: Self) -> Self:
        """
        Suppress container stderr.

        Container stderr is redirected to `/dev/null`.
        """
        return self.set_stderr(pathlib.Path("/dev/null"))

    def suppress_output(self: Self) -> Self:
        """
        Suppress container stdout and stderr.

        Container stdout/stderr is redirected to `/dev/null`.
        """
        return self.suppress_stdout().suppress_stderr()  # pragma: no cover


@attr.s(auto_attribs=True)
class ExecSpec(CommandSpec):
    """Specification for execution of a command within a container."""

    #: Arguments to pass to the container.
    args: List[str]

    #: Extra arguments to pass to :code:`docker exec`.
    extra_docker_args: List[str] = attr.ib(factory=list, kw_only=True)

    #: Whether to raise an exception if the command exits with a non-zero exit
    #: code.
    check: bool = attr.ib(default=True, kw_only=True)

    def check_exit_code(self, check: bool = True) -> "ExecSpec":
        """Raise an exception if the command exits with a non-zero exit code."""
        self.check = check
        return self


async def get_running_container_ids(
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None
) -> List[str]:
    """Retrieve the (short) container IDs of all running containers."""
    log.debug("Getting running container ids")
    cmd = ["docker", "ps", "-q"]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)
    return (await process.run(cmd, low_level=True)).splitlines()


async def get_all_container_ids(
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None
) -> List[str]:
    """Retrieve the (short) container IDs of all containers."""
    log.debug("Getting all container IDs")
    cmd = ["docker", "ps", "-aq"]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)
    return (await process.run(cmd, low_level=True)).splitlines()


@enum.unique
class Network(enum.Enum):
    """Specification for a container network."""

    #: The default network driver.
    BRIDGE = "bridge"

    #: Disable all networking.
    NONE = "none"

    #: Run on the host network.
    HOST = "host"


@attr.s(auto_attribs=True)
class BindMountSpec:
    """Specification for mounting a directory into a container."""

    #: Path on the host to the directory to be mounted.
    #:
    #: If Python is itself running in a container, this is a path in the current
    #: environment, that is, within the container running Python. Mapping this
    #: to a path understood by the Docker daemon is handled by
    #: :any:`tugboat.ContainerFactory.docker_host_path_mapping`.
    host_path: pathlib.Path

    #: Path in the guest to which to mount the directory.
    guest_path: pathlib.PurePath

    #: Equivalent to the ``ro`` option to ``docker run``'s `-v` flag.
    read_only: bool = attr.ib(default=False, kw_only=True)


@attr.s(auto_attribs=True)
class PortSpec:
    """Specification for port to publish to the host."""

    #: Host port on which to publish the container port.
    host_port: int = attr.ib(kw_only=True)

    #: Container port to publish.
    container_port: int = attr.ib(kw_only=True)

    def __attrs_post_init__(self) -> None:
        _validate_port_number(self.host_port, "host")
        _validate_port_number(self.container_port, "container")


async def create(
    image: str,
    *,
    entrypoint: Optional[str] = None,
    args: Optional[Sequence[str]] = None,
    bind_mounts: Optional[Sequence[BindMountSpec]] = None,
    network: Optional[Network] = None,
    publish_ports: Optional[Sequence[PortSpec]] = None,
    init: bool = False,
    labels: Optional[Mapping[str, Optional[str]]] = None,
    docker_host_path_mapping: Optional[Mapping[pathlib.PurePath, pathlib.Path]] = None,
    spec: Optional[CommandSpec] = None,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> str:
    """
    Create a container.

    Equivalent to ``docker create``.
    """
    log.debug("Creating container from image %s")
    docker_host_path_mapping = docker_host_path_mapping or {
        pathlib.PurePath("/"): pathlib.Path("/")
    }

    docker_command = ["docker", "create"]

    if entrypoint is not None:
        docker_command += ["--entrypoint", entrypoint]

    for bind_mount in bind_mounts or []:
        options = ""
        if bind_mount.read_only:  # pragma: no branch
            options = ":ro"
        host_path = _get_true_host_mount_path(
            docker_host_path_mapping, bind_mount.host_path
        )
        docker_command += ["-v", f"{host_path}:{bind_mount.guest_path}{options}"]

    if network:
        docker_command += ["--network", network.value]

    for port in publish_ports or []:
        docker_command += ["--publish", f"{port.host_port}:{port.container_port}"]

    if init:
        docker_command += ["--init"]

    for key, value in (labels or {}).items():
        docker_command += ["--label", key if value is None else f"{key}={value}"]

    docker_command += _get_docker_args(spec or CommandSpec())
    docker_command += [image]
    docker_command += args or []
    if docker_client_wrapper is not None:
        docker_command = docker_client_wrapper(docker_command)

    return _register_container_id(await process.run(docker_command))


def _register_container_id(container_id: str) -> str:  # pragma: no cover
    # This function provides a hook that is patched in unit test.
    return container_id


@async_generator.asynccontextmanager
async def start(
    container: str,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> AsyncIterator[None]:
    log.debug("Starting container %s", container)
    prev_started_at_ts = await _get_container_started_at_ts(
        container, docker_client_wrapper
    )
    if stdout is None:  # pragma: no cover
        stdout = sys.stdout
    if stderr is None:  # pragma: no cover
        stderr = sys.stderr

    cmd = ["docker", "start", "--attach", container]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)
    async with process.open_(cmd, stdout=stdout, stderr=stderr):
        # The container can take a small amount of time to start, so wait for it
        # to do so before yielding.
        # Since the container may also exit rapidly, it's not sufficient to
        # check whether the container is running. Instead check that its
        # StartedAt time has updated, indicating that it has started even if it
        # immediately stopped.
        try:
            await _wait_for_container_to_start(
                container, prev_started_at_ts, docker_client_wrapper
            )
        except TimeoutError as e:
            raise exceptions.DockerException(cmd) from e
        yield


async def _wait_for_container_to_start(
    container: str,
    prev_started_at_ts: str,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> None:
    log.debug("Waiting for container %s to start.", container)
    # Wait for a maximum of 100ms. This timeout should never be hit and is
    # included only as a fallback.
    for _ in range(10):
        if (
            await _get_container_started_at_ts(container, docker_client_wrapper)
        ) != prev_started_at_ts:
            return
        await anyio.sleep(0.01)
    raise TimeoutError(
        f"Timed out after 100ms waiting for container {container} to start"
    )


async def _get_container_started_at_ts(
    container: str,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> str:
    # We only check that the StartedAt time changes, so there's no need to
    # actually parse the time.
    cmd = ["docker", "inspect", container, "--format", r"{{ .State.StartedAt }}"]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)

    return await process.run(
        cmd,
        low_level=True,
    )


async def add_file(
    container: str,
    guest_path: pathlib.PurePath,
    contents: Union[bytes, str],
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> None:
    """
    Add a file to an existing container.

    Equivalent to using ``docker cp`` to create a file on the container and passing the
    contents as stdin.
    """
    log.debug("Adding file to container %s.", container)
    if isinstance(contents, str):
        contents = contents.encode()

    tarstream = io.BytesIO()
    tar = tarfile.TarFile(fileobj=tarstream, mode="w")
    info = tarfile.TarInfo(name=str(guest_path))
    info.size = len(contents)
    tar.addfile(info, io.BytesIO(contents))

    tar.close()

    cmd = ["docker", "cp", "-", f"{container}:/"]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)

    await process.run(cmd, input_=tarstream.getvalue())


async def extract_file(
    container: str,
    guest_path: pathlib.PurePath,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> bytes:
    """
    Extract a file from an existing container and return its contents.

    Equivalent to using ``docker cp`` to output the contents of a file to stdout, and
    returning the contents of stdout.
    """
    log.debug("Extracting file from container %s.", container)
    cmd = ["docker", "cp", f"{container}:/{guest_path}", "-"]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)

    tar_contents = await process.run(cmd)

    # If we get to this point, the call to ``docker cp`` worked so the file must
    # have existed. So we should raise an exception if extracting the file from
    # the resulting tar fails.
    tar = tarfile.TarFile(fileobj=io.BytesIO(tar_contents.encode()))
    extracted_file = tar.extractfile(guest_path.name)

    if extracted_file is not None:
        return extracted_file.read()
    else:
        raise exceptions.TugboatException(
            "Failed to extract file from container."
        )  # pragma: no cover


async def get_pid(
    container: str,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> int:
    """Return the PID for the given docker container."""
    log.debug("Getting PID for container %s.", container)
    cmd = ["docker", "inspect", "-f", "{{.State.Pid}}", f"{container}"]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)

    return int(
        await process.run(
            cmd,
            low_level=True,
        )
    )


async def wait(
    container: str,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> int:
    """
    Wait for a container to exit.

    Equivalent to ``docker wait``.

    Returns the container's exit code.
    """
    log.debug("Waiting for container %s to exit", container)
    cmd = ["docker", "wait", container]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)

    return int(await process.run(cmd, low_level=True))


async def exec_(
    container: str,
    spec: ExecSpec,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> process.CompletedProcess:
    log.debug("Executing command on container %s", container)
    with streams.OpenedStream.new(
        spec.stdout
    ) as stdout_stream, streams.OpenedStream.new(spec.stderr) as stderr_stream:
        cmd = ["docker", "exec", *_get_docker_args(spec), container, *spec.args]
        if docker_client_wrapper is not None:
            cmd = docker_client_wrapper(cmd)

        async with process.open_(
            cmd,
            stdout=stdout_stream.stream,
            stderr=stderr_stream.stream,
        ) as rc_fut:
            rc = await rc_fut
            stdout = stdout_stream.read()
            stderr = stderr_stream.read()
    if spec.check and rc:
        raise subprocess.CalledProcessError(rc, spec.args, stdout, stderr)
    return subprocess.CompletedProcess(spec.args, rc, stdout, stderr)


async def stop(
    container: str,
    *,
    timeout: Optional[timedelta] = None,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> None:
    """
    Stop a running container and wait for it to exit.

    Equivalent to ``docker stop``.
    """
    log.debug("Stopping container %s.", container)
    cmd = ["docker", "stop"]
    if timeout:
        # Docker only allows int values for the -t argument.
        cmd += ["-t", str(int(timeout.total_seconds()))]
    cmd += [container]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)

    await process.run(cmd)
    await wait(container, docker_client_wrapper)


async def kill(
    container: str,
    signal: Optional[Signals] = None,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> None:
    """
    Kill a running container.

    Equivalent to ``docker kill``.
    """
    log.debug("Killing container %s.", container)
    cmd = ["docker", "kill", container]
    if signal is not None:  # pragma: no branch
        cmd += ["--signal", str(signal.name)]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)

    # On the curio event loop, we can hit a race condition:
    #   - kill is called
    #   - the subprocess starts
    #   - the container exits
    #   - the kill process exists
    #   - the task monitoring the container raises an exception
    #   - curio handles the exception, attepting to kill the kill process
    #   - this fails, as that process has already exited.
    # The best we can do is protect the kill process from cancellation.
    async with _compat.CancelScope(shield=True):
        await process.run(cmd)


async def remove(
    container: str,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> None:
    """
    Remove a stopped container.

    Equivalent to ``docker rm``.
    """
    log.debug("Removing container %s", container)
    cmd = ["docker", "rm", container]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)
    await process.run(cmd)


def force_remove_sync(
    container: str,
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None,
) -> None:
    """
    Synchronously force-remove a container.

    Fallback for use where synchronous cleanup is required, such as when the event loop
    has been terminated.
    """
    log.debug("Forceably removing container %s", container)
    cmd = ["docker", "rm", "--force", container]
    if docker_client_wrapper is not None:
        cmd = docker_client_wrapper(cmd)
    process.run_sync(cmd)


def get_docker_hostname() -> str:
    """
    Retrieve the hostname of the host running the Docker daemon.

    The hostname is deduced from the DOCKER_HOST environment variable.
    """
    docker_host = os.environ.get("DOCKER_HOST")
    if docker_host is None:
        return "localhost"
    url = urllib.parse.urlparse(docker_host)
    if url.scheme in {"file", "unix"}:
        return "localhost"
    if url.scheme == "tcp" and url.hostname:
        return url.hostname
    raise ValueError(
        "Could not determine Docker hostname from "
        f"DOCKER_HOST environment variable value '{docker_host}'"
    )


def _get_docker_args(spec: CommandSpec) -> List[str]:
    docker_args: List[str] = []
    if spec.user is not None:
        docker_args += ["--user", spec.user]
    if spec.working_directory is not None:
        docker_args += ["--workdir", str(spec.working_directory)]
    for name, value in spec.environment.items():
        if value is not None:
            docker_args += ["--env", f"{name}={value}"]
        else:
            docker_args += ["--env", name]
    docker_args += spec.extra_docker_args
    return docker_args


def _get_true_host_mount_path(
    docker_host_path_mapping: Mapping[pathlib.PurePath, pathlib.Path],
    local_mount_path: pathlib.Path,
) -> pathlib.PurePath:
    """Translate a Python environment-local path to the same path on the Docker host."""
    for host_path, local_path in docker_host_path_mapping.items():
        try:
            return host_path / local_mount_path.relative_to(local_path)
        except ValueError:
            pass
    raise exceptions.TugboatException(
        f"Cannot mount '{local_mount_path}' into container as it is not a subdirectory "
        f"of any path mapped by the Docker host "
        f"({', '.join(str(p) for p in docker_host_path_mapping.keys())})"
    )


_MIN_PORT = 1
_MAX_PORT = 65535


def _validate_port_number(port: int, description: str) -> None:
    if not (_MIN_PORT <= port <= _MAX_PORT):
        raise ValueError(
            f"Invalid {description} port '{port}'. "
            f"Port must be in the range {_MIN_PORT}-{_MAX_PORT} inclusive."
        )
