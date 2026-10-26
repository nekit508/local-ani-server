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
