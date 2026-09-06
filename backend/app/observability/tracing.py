from __future__ import annotations

import time
from contextlib import contextmanager


@contextmanager
def trace_span(name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        _ = (time.perf_counter() - start) * 1000
        _ = name
