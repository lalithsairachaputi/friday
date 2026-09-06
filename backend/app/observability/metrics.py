from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class LatencySample:
    name: str
    value_ms: float
    cold: bool
    at: float = field(default_factory=time.time)
    meta: dict = field(default_factory=dict)


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: dict[str, int] = defaultdict(int)
        self.samples: list[LatencySample] = []
        self._seen: set[str] = set()

    def inc(self, name: str, n: int = 1) -> None:
        with self._lock:
            self.counters[name] += n

    def observe(self, name: str, value_ms: float, *, key: str | None = None, **meta: object) -> None:
        cold = True
        if key:
            with self._lock:
                cold = key not in self._seen
                self._seen.add(key)
        sample = LatencySample(name=name, value_ms=value_ms, cold=cold, meta=dict(meta))
        with self._lock:
            self.samples.append(sample)
            if len(self.samples) > 2000:
                self.samples = self.samples[-1000:]

    def snapshot(self) -> dict:
        with self._lock:
            grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"cold": [], "warm": []})
            for s in self.samples:
                grouped[s.name]["cold" if s.cold else "warm"].append(s.value_ms)
            summary = {}
            for name, buckets in grouped.items():
                summary[name] = {
                    "cold": _stats(buckets["cold"]),
                    "warm": _stats(buckets["warm"]),
                }
            return {"counters": dict(self.counters), "latency_ms": summary}


def _stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
        "p50": round(ordered[len(ordered) // 2], 2),
        "mean": round(sum(ordered) / len(ordered), 2),
    }


metrics = MetricsRegistry()
