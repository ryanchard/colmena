from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from lazy_object_proxy import Proxy
from typing import Any, Union

import colmena.value_server as value_server
from colmena.models import SerializationMethod

default_pool = ThreadPoolExecutor()


class Factory():
    """Factory class for retrieving objects from the value server"""
    def __init__(self,
                 key: str,
                 serialization_method: Union[str, SerializationMethod] = SerializationMethod.PICKLE
    ) -> None:
        """
        Args:
            key (str): key used to retrive object from value server
            serialization_method (SerializationMethod): serialization method
                used to store object in value server
        """
        self.key = key
        self.serialization_method = serialization_method
        self.async_get_future = None

    def __call__(self):
        """Retrive object from value server
        Note:
            `__call__` is generally only called once by the ObjectProxy
            unless ObjectProxy.reset_proxy() is called.
        """
        if value_server.server is None:
            value_server.init_value_server()

        if self.async_get_future is not None:
            result = self.async_get_future.result()
            self.async_get_future = None
            return result

        return value_server.server.get(self.key)

    def async_resolve(self):
        """Asynchrously get the object for the next call to `__call__`"""
        if value_server.server is None:
            value_server.init_value_server()

        self.async_get_future = default_pool.submit(
                value_server.server.get, self.key)


class ObjectProxy(Proxy):
    """Lazy proxy object wrapping a factory function

    An ObjectProxy transparently wraps any arbitrary object via an object
    `Factory`. The factory is callable and returns the true object; however,
    the factory is not called until the proxy is accessed in some way.
    """
    def __init__(self, factory: Factory) -> None:
        """
        Args:
            factory (Factor): factory class that when called will return
                the true object being wrapped
        """
        super(ObjectProxy, self).__init__(factory)

    def __reduce__(self):
        """See `__reduce_ex__`"""
        return ObjectProxy, (self.__factory__,)

    def __reduce_ex__(self, protocol):
        """Helper method for pickling
        Override `Proxy.__reduce_ex__` so that we only pickle the Factory
        and not the object itself to reduce size of the pickle.
        """
        return ObjectProxy, (self.__factory__,)

    def async_resolve(self) -> None:
        self.__factory__.async_resolve()

    def reset_proxy(self) -> None:
        """Reset wrapped object so that the factory is called on next access"""
        if hasattr(self, '__target__'):
            object.__delattr__(self, '__target__')


def to_proxy(obj: Any,
             key=None,
             serialization_method: Union[str, SerializationMethod] = SerializationMethod.PICKLE
) -> None:
    """Put object in value server and return proxy object
    Args:
        obj (object)
        key (str, optional): key to use for value server
        serialization_method (SerializationMethod): serialization method
    Returns:
        ObjectProxy
    """
    if key is None:
        key = str(id(obj))
    if not value_server.server.exists(key):
        value_server.server.put(key, obj, serialization_method)
    return ObjectProxy(Factory(key, serialization_method))


def async_resolve_proxies(args: Union[object, list, tuple, dict]) -> None:
    """Call async get on Proxy Objects

    Scans all arguments for any ObjectProxy instances and calls
    ObjectProxy.async_resolve_proxy() on it. This is useful if you have one
    or more proxies that you know will be needed soon so you can start
    asynchronously getting the values.

    Args:
        args (object, list, tuple, dict): possible object or
            iterable of objects that may be ObjectProxy instances
    """
    def async_resolve_if_proxy(obj: Any) -> Any:
        if isinstance(obj, ObjectProxy):
            obj.async_resolve()

    if isinstance(args, list) or isinstance(args, tuple):
        for x in args:
            async_resolve_if_proxy(x)
    elif isinstance(args, dict):
        for x in args:
            async_resolve_if_proxy(args[x])
    else:
        async_resolve_if_proxy(args)