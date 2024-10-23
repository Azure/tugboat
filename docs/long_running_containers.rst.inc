Long-Running Containers
-----------------------

*Long-running* containers are those that are designed to be run indefinitely, exiting only if:

- signaled to exit;
- encountering an error.

For example:

- A container serving a website;
- A container running a database;
- A container routing SIP traffic.

In ``tugboat`` long-running containers are invoked using the :any:`tugboat.ContainerFactory.start` function.
This function returns an async context manager:

>>> import anyio
>>> import requests
>>> import tugboat
>>>
>>> async def run():
...     spec = (
...         tugboat.ContainerSpec("nginx:1.21.6")
...         .publish_port(tugboat.PortSpec(host_port=8080, container_port=80))
...         .suppress_output()
...     )
...     async with tugboat.ContainerFactory().start(spec):
...         await anyio.sleep(5)  # give nginx time to start
...         print(requests.get(f"http://{tugboat.get_docker_hostname()}:8080"))
...     # Container automatically stopped

>>>
>>> anyio.run(run)
<Response [200]>


The container is run until:

- The context is exited, at which point the container is automatically stopped via ``docker stop``;
- The container is deliberately stopped, killed, or signaled via ``tugboat`` (see :ref:`stop_kill_signal`);
- The container itself exits, either of its own accord or by stopping, killing, or signaling it without use of ``tugboat``.

Long-running containers are not expected to exit unless explicitly instructed to do so.
As such, in the third case an exception will be raised, even if the container exited with a zero exit code:

>>> import anyio
>>> import tugboat
>>>
>>> async def run():
...     spec = tugboat.ContainerSpec("ubuntu:18.04").suppress_stdout()
...     async with tugboat.ContainerFactory().start(spec):
...         await anyio.sleep(30)
>>>
>>> anyio.run(run)
Traceback (most recent call last):
...
tugboat.container.UnexpectedExitException: container ... exited unexpectedly with exit code 0

.. _stop_kill_signal:

Stopping, Killing, or Signaling the Container
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :class:`tugboat.Container` object returned when entering the context manager exposes several methods allowing the program to interact with the running container.

- :any:`tugboat.Container.stop`;
- :any:`tugboat.Container.kill`;
- :any:`tugboat.Container.signal`.

Each of these methods is expected to cause the container to exit.
As such, an exception will not be raised if the container exits after a call to one of them - provided the exit code is allowed.
See the documentation of each method for details.

As above the container will be automatically stopped on exiting the context manager, so explicitly stopping, killing, or signaling the container is not generally required.

Running Commands in the Container
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :class:`tugboat.Container` object also exposes the :any:`tugboat.Container.exec` method allowing a command to be run inside the container.
This function takes a :class:`tugboat.ExecSpec`, similar to the :class:`tugboat.ContainerSpec` passed to :func:`tugboat.run`:

>>> import anyio
>>> import tugboat
>>>
>>> async def run():
...     container_spec = (
...         tugboat.ContainerSpec("ubuntu:18.04")
...         .suppress_stdout()
...         .run_indefinitely()
...     )
...     async with tugboat.ContainerFactory().start(container_spec) as container:
...         exec_spec = (
...             tugboat.ExecSpec(["printenv", "hello"])
...             .add_environment_variable("hello", "world")
...             .set_stdout(tugboat.PIPE)
...         )
...         print((await container.exec(exec_spec)).stdout)
>>>
>>> anyio.run(run)
world
<BLANKLINE>
