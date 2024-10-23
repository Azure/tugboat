One-Shot Containers
-------------------

*One-shot* containers are those that are run until they exit, such as:

- A container that deploys a product;
- A container that builds a VM image;
- A container that generates code.

In ``tugboat`` one-shot containers are invoked using the :func:`tugboat.run` or :any:`tugboat.ContainerFactory.run` functions (or, less commonly, their synchronous counterparts).
These functions will run the container until it exits, returning the container's exit code, stdout, and stderr:

>>> import anyio
>>> import tugboat
>>>
>>> spec = (
...     tugboat.ContainerSpec("ubuntu:18.04")
...     .set_args(["echo", "hello world"])
...     .set_stdout(tugboat.PIPE)
... )
>>> anyio.run(tugboat.run, spec)
CompletedProcess(args=['echo', 'hello world'], returncode=0, stdout='hello world\n')


Although (the async variants of) these functions do not block, they return only once the container has exited.

An exception will not be raised automatically if the container exits with a nonzero exit code.
The ``check_returncode`` `method <https://docs.python.org/3.6/library/subprocess.html#subprocess.CompletedProcess.check_returncode>`_ on the returned value may be used to raise on a nonzero exit code:

>>> import anyio
>>> import tugboat
>>>
>>> spec = (
...     tugboat.ContainerSpec("ubuntu:18.04")
...     .set_args(["ls", "not a file"])
...     .suppress_stdout()
... )
>>> anyio.run(tugboat.run, spec).check_returncode()
Traceback (most recent call last):
...
subprocess.CalledProcessError: Command '['ls', 'not a file']' returned non-zero exit status 2.
