import warnings
from typing import AsyncIterator, Callable, Coroutine

import anyio.abc
import async_generator


async def start_soon(
    task_group: anyio.abc.TaskGroup, func: Callable[[], Coroutine[object, None, None]]
) -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=DeprecationWarning,
            message=r"spawn\(\) is deprecated",
        )
        await task_group.spawn(func)


@async_generator.asynccontextmanager
async def CancelScope(*, shield: bool = False) -> AsyncIterator[None]:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=DeprecationWarning,
            message=r"open_cancel_scope\(\) is deprecated",
        )
        cm = anyio.maybe_async_cm(anyio.open_cancel_scope(shield=shield))
    async with cm:
        yield
