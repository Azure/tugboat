import contextlib
import io
import logging
import shlex
import subprocess
import sys
from typing import TYPE_CHECKING, AsyncIterator, Awaitable, Optional, Sequence, TextIO

import anyio
import async_generator

from .exceptions import DockerException

log = logging.getLogger(__name__)

# subprocess.CompletedProcess is not subscriptable at runtime - see
# https://mypy.readthedocs.io/en/latest/runtime_troubles.html#using-classes-that-are-generic-in-stubs-but-not-at-runtime.
if TYPE_CHECKING:  # pragma: no cover
    # pylint: disable=unsubscriptable-object
    CompletedProcess = subprocess.CompletedProcess[str]
else:
    CompletedProcess = subprocess.CompletedProcess


async def run(
    cmd: Sequence[str],
    input_: Optional[bytes] = None,
    low_level: bool = False,
) -> str:
    _log_cmd(cmd, low_level)
    try:
        result = await anyio.run_process(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            input=input_,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        log.error("Command '%s' failed.", _fmt_cmd(cmd))
        _log_output(e.stdout, e.stderr)
        raise DockerException(cmd, e.returncode, e.stdout, e.stderr) from e

    _log_output(result.stdout, result.stderr)
    return result.stdout.decode().strip()


def run_sync(cmd: Sequence[str], low_level: bool = False) -> str:
    _log_cmd(cmd, low_level)
    try:
        result = subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except subprocess.CalledProcessError as e:
        log.error("Command '%s' failed.", _fmt_cmd(cmd))
        raise DockerException(cmd, e.returncode, e.stdout, e.stderr) from e

    _log_output(result.stdout, result.stderr)
    return result.stdout.decode().strip()


@async_generator.asynccontextmanager
async def open_(
    cmd: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    low_level: bool = False,
) -> AsyncIterator[Awaitable[int]]:
    _log_cmd(cmd, low_level)
    async with await anyio.open_process(
        cmd,
        stdout=(stdout.fileno() if stdout else subprocess.DEVNULL),
        stderr=(stderr.fileno() if stderr else subprocess.DEVNULL),
    ) as process:
        rc_fut = process.wait()
        with contextlib.closing(rc_fut):
            yield rc_fut
        await process.wait()


def _log_cmd(cmd: Sequence[str], low_level: bool) -> None:
    log.log(
        logging.DEBUG if low_level else logging.INFO,
        f"Running command '{_fmt_cmd(cmd)}'",
    )


def _log_output(stdout: bytes, stderr: bytes) -> None:
    for stdout_line in stdout.decode().splitlines():
        log.debug('STDOUT: "%s"', stdout_line)

    for stderr_line in stderr.decode().splitlines():
        log.debug('STDERR: "%s"', stderr_line)


def _fmt_cmd(cmd: Sequence[str]) -> str:
    return " ".join([cmd[0]] + [shlex.quote(a) for a in cmd[1:]])


def _get_stderr_fileno() -> int:  # pragma: no cover
    try:
        return sys.stderr.fileno()
    except io.UnsupportedOperation:
        # io.StringIO implements the TextIO interface so may legitimately be
        # used to replace sys.stderr - pytest uses this when capturing output,
        # for example.
        # However io.StringIO does not have an underlying file descriptor so
        # throws when calling its fileno method.
        # Capture the stderr instead - it's the best we can do.
        log.debug(
            f"Unable to retrieve fileno for stderr ({sys.stderr!r}). "
            "Stderr will be captured instead."
        )
        return subprocess.PIPE
