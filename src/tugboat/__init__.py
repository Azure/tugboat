from . import process
from .client_interface import (
    BindMountSpec,
    ExecSpec,
    Network,
    PortSpec,
    get_docker_hostname,
)
from .container import Container, ContainerFactory, ContainerSpec
from .exceptions import ContainerException, TugboatException
from .streams import PIPE


async def run(spec: ContainerSpec) -> process.CompletedProcess:
    """
    Asynchronously run a container until it exits.

    Return the container's exit code, stdout, and stderr.
    """
    return await ContainerFactory().run(spec)


def run_sync(spec: ContainerSpec) -> process.CompletedProcess:
    """Synchronously run a container until it exits."""
    return ContainerFactory().run_sync(spec)


__all__ = [
    "PIPE",
    "BindMountSpec",
    "Container",
    "ContainerException",
    "ContainerFactory",
    "ContainerSpec",
    "ExecSpec",
    "PortSpec",
    "Network",
    "TugboatException",
    "get_docker_hostname",
    "run",
    "run_sync",
]
