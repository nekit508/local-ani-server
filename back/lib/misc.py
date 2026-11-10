from collections.abc import Callable
from typing import Any


def single_call(func):
    func.__single_call_cached_out__ = None

    def wrapper(*args, **kwargs):
        if func.__single_call_cached_out__ is None:
            func.__single_call_cached_out__ = func(*args, **kwargs)
        return func.__single_call_cached_out__

    return wrapper


def select[T](obj: T, allowed: list[str], out: dict[str, Any] = None) -> dict[str, Any]:
    if out is None:
        out = {}

    for k in allowed:
        if k in allowed:
            out[k] = getattr(obj, k)

    return out


def local_cache[A, R](function: Callable[A, R]) -> "LocallyCachedFunction[A, R]":
    return LocallyCachedFunction(function)


class LocallyCachedFunction[A, R]:
    _function: Callable[A, R]

    def __init__(self, function: Callable[A, R]):
        self._function = function

    def __enter__(self) -> LocalCache[A, R]:
        return LocalCache(self._function)

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class LocalCache[A, R]:
    _function: Callable[A, R]
    _cache: dict[A, R]

    def __init__(self, function: Callable[A, R]):
        self._function = function
        self._cache = {}

    def reset(self):
        self._cache.clear()

    def __call__(self, *args, **kwargs) -> R:
        t = (*args, *kwargs)
        if t in self._cache:
            return self._cache[t]

        o = self._function(*args, **kwargs)

        self._cache[t] = o

        return o