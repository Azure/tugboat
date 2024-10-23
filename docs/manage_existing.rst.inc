``tugboat`` can be used to manage an existing container, provided that you know its container ID:

>>> import tugboat
>>>
>>> container = tugboat.Container.from_container_id("abcd1234efgh")

You can then perform operations on that container, just as you could with a container you created with ``tugboat`` itself, with the caveat that ``tugboat`` will not capture ``stdout`` and ``stderr`` for containers that are managed in this way.