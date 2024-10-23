API Reference
=============

.. warning::

   The following is the complete public API of ``tugboat`` for the purposes of semantic versioning.
   Any part of the package not documented here may be changed without warning.

.. https://github.com/sphinx-doc/sphinx/issues/6316 means that autodoc members
   don't get added to the table of contents. We manually add headings for each
   member to make the API reference easy to navigate.

Specifying Containers
---------------------

tugboat.ContainerSpec
^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: tugboat.ContainerSpec

tugboat.BindMountSpec
^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: tugboat.BindMountSpec

tugboat.Network
^^^^^^^^^^^^^^^

.. autoclass:: tugboat.Network

tugboat.PortSpec
^^^^^^^^^^^^^^^^

.. autoclass:: tugboat.PortSpec

tugboat.PIPE
^^^^^^^^^^^^

.. autodata:: tugboat.PIPE

Running Containers
------------------

tugboat.run
^^^^^^^^^^^

.. autofunction:: tugboat.run

tugboat.run_sync
^^^^^^^^^^^^^^^^

.. autofunction:: tugboat.run_sync

tugboat.ContainerFactory
^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: tugboat.ContainerFactory

Interacting with Running Containers
-----------------------------------

tugboat.Container
^^^^^^^^^^^^^^^^^

.. autoclass:: tugboat.Container

tugboat.ExecSpec
^^^^^^^^^^^^^^^^

.. autoclass:: tugboat.ExecSpec


tugboat.get_docker_hostname
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autofunction:: tugboat.get_docker_hostname

Exceptions
----------

tugboat.TugboatException
^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: tugboat.TugboatException

tugboat.ContainerException
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: tugboat.ContainerException
