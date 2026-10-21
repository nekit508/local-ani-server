def single_call(func):
    func.__single_call_cached_out__ = None

    def wrapper():
        if func.__single_call_cached_out__ is None:
            func.__single_call_cached_out__ = func()
        return func.__single_call_cached_out__

    return wrapper


def select[T](obj: T, allowed: set[str]) -> dict[str, object]:
    return {k: getattr(obj, k) for k in allowed if k in allowed and hasattr(obj, k)}
