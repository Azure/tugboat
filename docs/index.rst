tugboat
=======

|python_badge| |version_badge|

.. |python_badge| image:: https://img.shields.io/badge/python-3.6-blue
   :target: https://www.python.org/
   :alt: python: 3.6

Pythonic Docker containers.

The library is designed with the following goals in mind:

- Easily understandable;
- Solid, safe, and structured;
- Flexibly asynchronous.

Easily Understandable
---------------------

It should be easy to understand what the library is doing and reproduce its behaviour using the Docker CLI.
The library is not intended to replace familiarity with Docker.
Instead, it is meant to *complement* Docker - it should be easy to carry over knowledge from one to the other.

Solid, Safe, and Structured
---------------------------

It should be easy to understand the lifetime of a container and make sure resources are cleaned up.
It should be obvious when a container has exited unexpectedly; the library expects that you care about every container.
If the library ever leaves a container lying around, it's a bug.

Flexibly Asynchronous
---------------------

The library should run on any of the three common event loops:

- asyncio, in the standard library;
- `trio <https://trio.readthedocs.io/en/stable/>`_
- `curio <https://curio.readthedocs.io/en/latest/>`_

The library should also be easy to use for simple synchronous operations.

Why not...
----------

- use the Python Docker client? It has no async support;
- use another third-party library? There doesn't seem to be one that meets the goals above!
- use the Docker API (instead of running subprocesses)? It's less clear what the library is doing, and harder to translate it into commands that can be run interactively in the terminal;
- use Kubernetes? A Python client is still required, it's an additional dependency, and it doesn't keep such a close eye on containers.

Guide
-----

.. toctree::
   :maxdepth: 2

   usage
   api
   genindex
   Source Code <https://git.datcon.co.uk/clearwater-core/tugboat>
