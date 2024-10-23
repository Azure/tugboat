import contextlib
import pathlib
import tempfile
from typing import Iterator, Optional, TextIO, Union

import attr
from typing_extensions import Final


@attr.s(frozen=True)
class Pipe:
    """Singleton representing capture of stdout/stderr."""


PIPE: Final = Pipe()

OutStream = Union[pathlib.Path, TextIO, Pipe]


@attr.s(auto_attribs=True, frozen=True)
class OpenedStream:
    stream: TextIO
    filepath: Optional[pathlib.Path]

    @classmethod
    @contextlib.contextmanager
    def new(cls, stream: OutStream) -> Iterator["OpenedStream"]:
        if isinstance(stream, Pipe):
            with tempfile.TemporaryDirectory() as tmpdir:
                with cls.new(pathlib.Path(tmpdir) / "out") as os:
                    yield os
        elif isinstance(stream, pathlib.Path):
            with open(stream, "w", encoding="utf-8") as f:
                yield cls(f, stream)
        else:
            yield cls(stream, None)

    def read(self) -> Optional[str]:
        if not self.filepath:
            return None
        with open(self.filepath, encoding="utf-8") as f:
            return f.read()
