Basic Usage
-----------

Create a `ContainerSpec`, using the builder interface:

>>> import tugboat
>>>
>>> spec = (
...     tugboat.ContainerSpec("ubuntu:18.04")
...     .add_environment_variable("hello", "world")
...     .set_stdout(tugboat.PIPE)
...     .set_args(["printenv", "hello"])
... )

or keyword arguments:

>>> spec = tugboat.ContainerSpec(
...     "ubuntu:18.04",
...     environment={"hello": "world"},
...     args=["printenv", "hello"],
...     stdout=tugboat.PIPE,
... )


Run it synchronously:

>>> tugboat.run_sync(spec).stdout
'world\n'

or asynchronously:

>>> import anyio
>>>
>>> async def tugboat_run():
...     return await tugboat.run(spec)
>>>
>>> anyio.run(tugboat_run).stdout
'world\n'
