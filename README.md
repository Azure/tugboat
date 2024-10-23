![tugboat](docs/_static/tugboat.png)

# tugboat

[![python: 3.6](https://img.shields.io/badge/python-3.6-blue)](https://www.python.org/)
[![version 0.7.0](https://img.shields.io/badge/version-0.7.0-success)](https://artifactory.metaswitch.com/ui/packages/pypi:%2F%2Ftugboat-docker)

[![Checked with mypy](https://img.shields.io/badge/mypy-checked-blue)](http://mypy-lang.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Pythonic Docker containers.

## Introduction

The library is designed with the following goals in mind:

- Easily understandable;
- Solid, safe, and structured;
- Flexibly asynchronous.

### Easily Understandable

It should be easy to understand what the library is doing and reproduce its behaviour using the Docker CLI.
The library is not intended to replace familiarity with Docker.
Instead, it is meant to _complement_ Docker - it should be easy to carry over knowledge from one to the other.

### Solid, Safe, and Structured

It should be easy to understand the lifetime of a container and make sure resources are cleaned up.
It should be obvious when a container has exited unexpectedly; the library expects that you care about every container.
If the library ever leaves a container lying around, it's a bug.

### Flexibly Asynchronous

The library should run on any of the three common event loops:

- asyncio, in the standard library;
- [trio](https://trio.readthedocs.io/en/stable/);
- [curio](https://curio.readthedocs.io/en/latest/).

The library should also be easy to use for simple synchronous operations.

## Why not...

- use the Python Docker client? It has no async support;
- use another third-party library? There doesn't seem to be one that meets the goals above!
- use the Docker API (instead of running subprocesses)? It's less clear what the library is doing, and harder to translate it into commands that can be run interactively in the terminal;
- use Kubernetes? A Python client is still required, it's an additional dependency, and it doesn't keep such a close eye on containers.

## Basic Usage

Create a `ContainerSpec`, using the builder interface:

```python
>>> import tugboat
>>>
>>> spec = (
...     tugboat.ContainerSpec("ubuntu:18.04")
...     .add_environment_variable("hello", "world")
...     .set_stdout(tugboat.PIPE)
...     .set_args(["printenv", "hello"])
... )

```

or keyword arguments:

```python
>>> spec = tugboat.ContainerSpec(
...     "ubuntu:18.04",
...     environment={"hello": "world"},
...     args=["printenv", "hello"],
...     stdout=tugboat.PIPE,
... )

```

Run it synchronously:

```python
>>> tugboat.run_sync(spec).stdout
'world\n'

```

or asynchronously:

```python
>>> import anyio
>>>
>>> async def get_world():
...     return (await tugboat.run(spec)).stdout
>>>
>>> anyio.run(get_world)
'world\n'

```

For more details see the [complete documentation][docs].

## Developing

The standard `make` targets (`test`, `style`, `lint`, `full_test`) are available and are run in CI.

### Avoiding Slow Tests

By default the tests run against each of the three supported event loops.
While developing on the repo it is sometimes useful to run against only one; this can be achieved by passing `-m "not slow"` to `pytest`, causing the tests to run against `trio` only.

Be aware, however, that the tests are required to pass against all three event loops in CI, and there are differences in their behavior.

### Building the Documentation Locally

When working on a branch it can be useful to build and view the documentation locally.
Running `make docs` builds the relevant files - the docs can be viewed by navigating to `file://<path to repo>/docs/_build/index.html` in any web browser.

### Running the Tests in a Docker Container

The repo's unit tests require use of a temporary directory with the same path in both:

- the environment running the tests;
- the Docker host.

When running in a Docker container such a directory is not automatically available.
To provide a suitable directory:

- mount a directory into the Docker container at the same location, for example passing `-v /tmp/test_dir:/tmp/test_dir` to `docker run`;
- in the container, set the `TUGBOAT_TEST_TEMP_DIR` environment variable to the path to this directory, for example passing `-e TUGBOAT_TEST_TEMP_DIR=/tmp/test_dir` to `docker run`.

## Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.opensource.microsoft.com.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
