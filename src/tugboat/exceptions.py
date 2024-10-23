from typing import Optional, Sequence

import attr


class TugboatException(Exception):
    """Base class for exceptions raised by ``tugboat``."""


class ContainerException(TugboatException):
    """Raised on unexpected behavior from a container."""


@attr.s(auto_attribs=True)
class DockerException(TugboatException):
    """Raised on Docker errors."""

    cmd: Sequence[str]
    returncode: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
