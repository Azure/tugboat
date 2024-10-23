import logging
import pathlib
import subprocess
import sys
from datetime import timedelta
from signal import SIGKILL, SIGTERM, Signals
from typing import (
    AsyncIterator,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Union,
)

import anyio
import async_generator
import attr

from . import _compat, client_interface, exceptions, process, streams

log = logging.getLogger(__name__)


# Duplicate some member variables present in the base class in order to
# provide slightly different docstrings in the derived class.
@attr.s(auto_attribs=True)
class ContainerSpec(client_interface.CommandSpec):
    """Specification for a container."""

    #: Docker image reference, such as ``ubuntu:18.04`` or ``python:latest``.
    image: str

    #: Arguments to pass to the container.
    args: List[str] = attr.ib(factory=list, kw_only=True)

    #: Container entry point, equivalent to ``docker run``'s ``--entrypoint``
    #: flag.
    entrypoint: Optional[str] = attr.ib(default=None, kw_only=True)

    #: Name used in logs; serves no functional purpose.
    log_name: Optional[str] = attr.ib(default=None, kw_only=True)

    #: Mount directories into the container, equivalent to :code:`docker run`'s
    #: :code:`-v` flag.
    bind_mounts: List[client_interface.BindMountSpec] = attr.ib(
        factory=list, kw_only=True
    )

    #: Network settings, equivalent to :code:`docker run`'s :code:`--network`
    #: flag.
    network: Optional[client_interface.Network] = attr.ib(default=None, kw_only=True)

    #: Container ports to publish to the host, equivalent to
    #: :code:`docker run`'s :code:`--publish` flag.
    published_ports: List[client_interface.PortSpec] = attr.ib(
        factory=list, kw_only=True
    )

    #: Files to create in the container. Mapping of guest path to file contents.
    files: Dict[pathlib.PurePath, Union[str, bytes]] = attr.ib(
        factory=dict, kw_only=True
    )

    #: Run an init system inside the container, equivalent to ``docker run``'s
    #: ``--init`` flag.
    init: bool = attr.ib(default=False, kw_only=True)

    #: Apply metadata to the container, equivalent to ``docker run``'s
    #: ``--label`` flag.
    labels: Dict[str, Optional[str]] = attr.ib(factory=dict, kw_only=True)

    #: Extra arguments to pass to :code:`docker start`.
    extra_docker_args: List[str] = attr.ib(factory=list, kw_only=True)

    #: Stream to which command stdout is written.
    #:
    #: Either:
    #:
    #: - a ``pathlib.Path``, which will be opened and written to;
    #: - a ``TextIO`` stream, which will be written to directly;
    #: - the special value :any:``tugboat.PIPE`` which, if supplied, causes
    #:   the process stdout to be stored and returned alongside the command
    #:   exit code.
    stdout: streams.OutStream = attr.ib(factory=lambda: sys.stdout, kw_only=True)

    #: Stream to which command stderr is written. See also
    #: :any:`tugboat.ContainerSpec.stdout`
    stderr: streams.OutStream = attr.ib(factory=lambda: sys.stderr, kw_only=True)

    def set_entrypoint(self, entrypoint: Optional[str]) -> "ContainerSpec":
        """
        Set the container entrypoint.

        Equivalent to ``docker run``'s ``--entrypoint`` flag.
        """
        self.entrypoint = entrypoint
        return self

    def set_args(self, args: Sequence[str]) -> "ContainerSpec":
        """Set the arguments passed to the container."""
        self.args = [*args]
        return self

    def set_log_name(self, log_name: Optional[str]) -> "ContainerSpec":
        """
        Provide a container name for use in logs.

        The label serves no functional purpose.
        """
        self.log_name = log_name
        return self

    def add_bind_mount(
        self, bind_mount: client_interface.BindMountSpec
    ) -> "ContainerSpec":
        """
        Mount a directory into the container.

        Equivalent to :code:`docker run`'s :code:`-v` flag.
        """
        self.bind_mounts.append(bind_mount)
        return self

    def set_network(
        self, network: Optional[client_interface.Network]
    ) -> "ContainerSpec":
        """
        Set the container network.

        Equivalent to :code:`docker run`'s :code:`--network` flag.
        """
        self.network = network
        return self

    def publish_port(self, port: client_interface.PortSpec) -> "ContainerSpec":
        """
        Publish a container port to the host.

        Equivalent to :code:`docker run`'s :code:`--publish` flag.
        """
        self.published_ports.append(port)
        return self

    def add_file(
        self, guest_path: pathlib.PurePath, contents: Union[bytes, str]
    ) -> "ContainerSpec":
        """
        Create a file in the container.

        :param guest_path: Path on the container filesystem at which to create
            the file.
        :param contents: Contents to write to the created file.
        """
        self.files[guest_path] = contents
        return self

    def run_init_system(self, init: bool = True) -> "ContainerSpec":
        """
        Run an init system inside the container.

        Equivalent to ``docker run``'s ``--init`` flag.
        """
        self.init = init
        return self

    def add_label(self, key: str, value: Optional[str] = None) -> "ContainerSpec":
        """
        Apply metadata to the container.

        Equivalent to ``docker run``'s ``--label`` flag.
        """
        self.labels[key] = value
        return self

    def run_indefinitely(self) -> "ContainerSpec":
        """
        Run the container until its context is exited.

        This is useful when a container is used only as an environment for ``exec``
        commands.
        """
        # `sleep` doesn't handle signals nicely, so use an init process.
        return self.run_init_system().set_entrypoint("sleep").set_args(["infinity"])


@attr.s(auto_attribs=True, frozen=True)
class ContainerFactory:
    """
    Factory used to create Docker containers.

    Simple use-cases may not require a factory at all.
    """

    #: When Python is itself running in a container, the paths local to the
    #: Python process do not correspond to those understood by the Docker
    #: daemon. In particular, any directory to be mounted into the new container
    #: must be mounted into the container running Python.
    #:
    #: This is a mapping of host paths, that is, paths on the host running the
    #: Docker daemon, to paths in the current environment. It is used to
    #: translate mount paths local to the current environment to paths
    #: understood by the Docker daemon.
    docker_host_path_mapping: Optional[Mapping[pathlib.PurePath, pathlib.Path]] = None

    #: If creating a container that lives inside another docker-in-docker
    #: container (for example), it can be necessary to prefix all commands to
    #: the docker client.
    docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None

    async def run(self, spec: ContainerSpec) -> process.CompletedProcess:
        """
        Asynchronously run a container until it exits.

        Return the container's exit code, stdout, and stderr.

        See also :class:`tugboat.ContainerSpec`.
        """
        async with self._create(spec) as container:
            async with container.start():
                return await container.wait()

    def run_sync(self, spec: ContainerSpec) -> process.CompletedProcess:
        """Synchronously run a container until it exits."""
        return anyio.run(self.run, spec)

    @async_generator.asynccontextmanager
    async def start(self, spec: ContainerSpec) -> AsyncIterator["Container"]:
        """
        Start a container.

        The container will be stopped on exiting the returned context.
        """
        async with self._create(spec) as container:
            async with anyio.create_task_group() as task_group:
                async with container.start():
                    await _compat.start_soon(task_group, container.watch_for_exit)
                    yield container

    @async_generator.asynccontextmanager
    async def _create(self, spec: ContainerSpec) -> AsyncIterator["Container"]:
        # Use the short (12 character) container ID for clearer logs.
        container_id = (
            await client_interface.create(
                spec.image,
                entrypoint=spec.entrypoint,
                args=spec.args,
                bind_mounts=spec.bind_mounts,
                network=spec.network,
                publish_ports=spec.published_ports,
                init=spec.init,
                labels=spec.labels,
                docker_host_path_mapping=self.docker_host_path_mapping,
                spec=spec,
                docker_client_wrapper=self.docker_client_wrapper,
            )
        )[:12]

        if spec.log_name:
            label = f"'{spec.log_name}' ({container_id})"
        else:
            label = container_id

        args = []
        if spec.entrypoint:
            args += [spec.entrypoint]
        args += spec.args

        with streams.OpenedStream.new(spec.stdout) as stdout, streams.OpenedStream.new(
            spec.stderr
        ) as stderr:
            container = Container(
                container_id,
                spec.log_name or container_id,
                args,
                stdout,
                stderr,
                docker_client_wrapper=self.docker_client_wrapper,
            )
            log.info(f"Created container {label}")
            try:
                for filepath, contents in spec.files.items():
                    await client_interface.add_file(container_id, filepath, contents)
                yield container
            finally:
                async with _compat.CancelScope(shield=True):
                    await container.remove()


# These exceptions _must_ be mutable, as trio rewrites the traceback on hitting
# an error.
@attr.s(auto_attribs=True)
class UnexpectedExitException(exceptions.ContainerException):
    """Raised when a container exits unexpectedly."""

    container_id: str
    label: str
    exit_code: int

    def __str__(self) -> str:
        return f"container {self.label} exited unexpectedly with exit code {self.exit_code}"


@attr.s(auto_attribs=True)
class UnexpectedExitCodeException(exceptions.ContainerException):
    """Raised when a container exits with an unexpected exit code."""

    container_id: str
    label: str
    exit_code: int

    def __str__(self) -> str:
        return (
            f"container {self.label} exited with unexpected exit code {self.exit_code}"
        )


@attr.s(auto_attribs=True)
class Container:
    """A Docker container."""

    # Short container ID as used by Docker.
    _id: str

    # Label used in logs. Serves no functional purpose.
    _label: str

    # Container arguments. Used only when creating `subprocess.CompletedProcess`
    # instances.
    _args: Sequence[str] = attr.ib(factory=list)

    # Stream to which container stdout should be written.
    _stdout: Optional[streams.OpenedStream] = None

    # Stream to which container stderr should be written.
    _stderr: Optional[streams.OpenedStream] = None

    # Set of exit codes expected from the container. If empty, the container is
    # not expected to exit at all. Updated on calling the ``stop``, ``kill``, or
    # ``signal`` methods.
    _allowed_exit_codes: Set[int] = attr.ib(factory=set, init=False)

    _docker_client_wrapper: Optional[Callable[[List[str]], List[str]]] = None

    @classmethod
    def from_container_id(
        cls, container_id: str, *, label: Optional[str] = None
    ) -> "Container":
        """
        Create a Container object for managing an existing container.

        .. warning::
            It's recommended only to use this method for managing a container which
            was not created by `tugboat`. It is possible, but ill-advised,  to have
            multiple `Container`s managing the same underlying Docker container
            (either by calling this method multiple times with the same container
            ID, or calling it with the ID of a container created via another
            `tugboat` method) - in this scenario, the `Container`s may disagree
            about allowed exit codes and an "expected" exit triggered through one
            `Container` may be interpreted as an error by the other.
        """
        return cls(container_id, label or container_id)

    @property
    def id(self) -> str:
        return self._id

    @async_generator.asynccontextmanager
    async def start(
        self,
    ) -> AsyncIterator[None]:
        async with client_interface.start(
            self.id,
            stdout=(self._stdout.stream if self._stdout else None),
            stderr=(self._stderr.stream if self._stderr else None),
            docker_client_wrapper=self._docker_client_wrapper,
        ):
            log.info(f"Started container {self._label}")
            try:
                yield
            finally:
                async with _compat.CancelScope(shield=True):
                    await self.stop()

    async def stop(self, *, timeout: Optional[timedelta] = None) -> None:
        """
        Stop the container. Equivalent to :code:`docker stop`.

        Allows the container to exit with code 0 or 143 (128 + SIGTERM).
        """
        if not self._allowed_exit_codes:
            self._allowed_exit_codes = {0, 128 + SIGTERM.value}
        if self.id in await client_interface.get_running_container_ids(
            docker_client_wrapper=self._docker_client_wrapper
        ):
            await client_interface.stop(
                self.id,
                timeout=timeout,
                docker_client_wrapper=self._docker_client_wrapper,
            )
            log.info(f"Stopped container {self._label}")
        else:
            log.debug(f"Not stopping container {self._label} as it is already stopped")

    async def kill(self) -> None:
        """
        Kill the container. Equivalent to :code:`docker kill`.

        Allows the container to exit with code 137 (128 + SIGKILL).
        """
        await self.signal(SIGKILL, allowed_exit_codes={128 + SIGKILL.value})

    async def signal(
        self, signal: Signals, allowed_exit_codes: Optional[Set[int]] = None
    ) -> None:
        """
        Send a signal to the container.

        Equivalent to :code:`docker kill --signal <signal>`.

        :param signal: Signal to send to the container.
        :param allowed_exit_codes: Set of exit codes allowed for the container
            after receiving the signal. Supply the empty set if the container is
            not expected to exit. Defaults to ``{0}``. Note that this function
            will not check that the container actually exits.
        """
        if allowed_exit_codes is None:  # pragma: no cover
            allowed_exit_codes = {0}
        self._allowed_exit_codes |= allowed_exit_codes
        await client_interface.kill(
            self.id, signal=signal, docker_client_wrapper=self._docker_client_wrapper
        )
        log.info(f"Sent {signal.name} to container {self._label}")

    async def wait(
        self, allowed_exit_codes: Optional[Set[int]] = None
    ) -> process.CompletedProcess:
        """
        Wait for the container to exit and return its exit code.

        :param allowed_exit_codes: Set of *additional* exit codes allowed for
            the container. Defaults to the empty set.
        """
        self._allowed_exit_codes |= allowed_exit_codes or set()
        return subprocess.CompletedProcess(
            self._args,
            await client_interface.wait(
                self.id, docker_client_wrapper=self._docker_client_wrapper
            ),
            stdout=(self._stdout.read() if self._stdout else None),
            stderr=(self._stderr.read() if self._stderr else None),
        )

    async def watch_for_exit(self) -> None:
        exit_code = (await self.wait()).returncode
        log.info(f"Container {self._label} exited with exit code {exit_code}")
        if not self._allowed_exit_codes:
            raise UnexpectedExitException(self.id, self._label, exit_code)
        if exit_code not in self._allowed_exit_codes:
            raise UnexpectedExitCodeException(self.id, self._label, exit_code)

    async def exec(self, spec: client_interface.ExecSpec) -> process.CompletedProcess:
        """
        Execute a command inside the container.

        Return the completed process object.

        See also :class:`tugboat.ExecSpec`.
        """
        return await client_interface.exec_(
            self.id, spec, docker_client_wrapper=self._docker_client_wrapper
        )

    async def remove(self) -> None:
        try:
            if self.id in await client_interface.get_all_container_ids(
                docker_client_wrapper=self._docker_client_wrapper
            ):
                await client_interface.remove(
                    self.id, docker_client_wrapper=self._docker_client_wrapper
                )
                log.info(f"Removed container {self._label}")
            else:
                log.debug(
                    f"Not removing container {self._label} as it has already been removed"
                )
        except BaseException as e:
            # On some event loop implementations, async subprocess calls fail
            # once the loop has been interrupted. Make sure containers are
            # _always_ cleaned up.
            # This will throw if the container has already been removed, but
            # we are already in an error case so it doesn't matter.
            client_interface.force_remove_sync(
                self.id, docker_client_wrapper=self._docker_client_wrapper
            )
            log.warning(
                f"Force removed container {self._label} "
                f"after hitting exception during normal removal: {e}"
            )
            raise

    @property
    async def pid(self) -> int:
        """Return the container's PID."""
        return await client_interface.get_pid(
            self.id, docker_client_wrapper=self._docker_client_wrapper
        )

    async def add_file(
        self, guest_path: pathlib.PurePath, contents: Union[bytes, str]
    ) -> None:
        """Create a file on the container with the specified contents."""
        await client_interface.add_file(
            self.id,
            guest_path,
            contents,
            docker_client_wrapper=self._docker_client_wrapper,
        )

    async def extract_file(self, guest_path: pathlib.PurePath) -> bytes:
        """Return the contents of a specified file in the container."""
        return await client_interface.extract_file(
            self.id, guest_path, docker_client_wrapper=self._docker_client_wrapper
        )
