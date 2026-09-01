"""Pure measurement and scoring primitives shared by the benchmark runners."""

from __future__ import annotations

import ctypes
import math
import os
import statistics
import sys
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Self

MB = 1_000_000


if sys.platform == "win32":
    class _WindowsProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]


    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    _get_process_memory_info = _kernel32.K32GetProcessMemoryInfo
    _get_process_memory_info.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_WindowsProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    _get_process_memory_info.restype = ctypes.c_int


@dataclass(frozen=True)
class Pricing:
    input_per_million: float
    output_per_million: float
    source: str


def percentile(values: Sequence[float], probability: float) -> float:
    """Linearly interpolated percentile, including both endpoints."""
    if not values:
        raise ValueError("a percentile needs at least one value")
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values: Iterable[float]) -> dict[str, float | int] | None:
    samples = list(values)
    if not samples:
        return None
    return {
        "n": len(samples),
        "mean": statistics.mean(samples),
        "stdev": statistics.pstdev(samples),
        "min": min(samples),
        "p50": percentile(samples, 0.50),
        "p95": percentile(samples, 0.95),
        "max": max(samples),
    }


def cost_usd(input_tokens: int, output_tokens: int, pricing: Pricing | None) -> float | None:
    if pricing is None:
        return None
    return (
        input_tokens * pricing.input_per_million
        + output_tokens * pricing.output_per_million
    ) / 1_000_000


def linear_slope(values: Sequence[float]) -> float:
    """Least-squares slope per sample index; zero for fewer than two observations."""
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2
    y_mean = statistics.mean(values)
    denominator = sum((x - x_mean) ** 2 for x in range(len(values)))
    return sum((x - x_mean) * (y - y_mean) for x, y in enumerate(values)) / denominator


def quality_metrics(
    selected_candidates: Sequence[Sequence[str]], relevant: Mapping[str, float]
) -> dict[str, float | int | list[str]]:
    """Score ranked slide candidates against path-level graded relevance.

    Recall remains path based because the labels identify evidence files. Precision is candidate
    based because one selected candidate becomes one slide, even if it carries several paths.
    nDCG rewards putting stronger evidence earlier and does not depend on absolute list length.
    """
    selected_paths = {path for candidate in selected_candidates for path in candidate}
    relevant_paths = set(relevant)
    hits = selected_paths & relevant_paths
    candidate_grades = [max((relevant.get(path, 0.0) for path in paths), default=0.0) for paths in selected_candidates]
    candidate_hits = sum(grade > 0 for grade in candidate_grades)

    def dcg(grades: Sequence[float]) -> float:
        return sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(grades))

    ideal = sorted(relevant.values(), reverse=True)[: len(selected_candidates)]
    ideal_dcg = dcg(ideal)
    return {
        "hits": len(hits),
        "relevant": len(relevant_paths),
        "selected_candidates": len(selected_candidates),
        "selected_paths": len(selected_paths),
        "recall": len(hits) / len(relevant_paths) if relevant_paths else 0.0,
        "candidate_precision": candidate_hits / len(selected_candidates) if selected_candidates else 0.0,
        "ndcg": dcg(candidate_grades) / ideal_dcg if ideal_dcg else 0.0,
        "missed": sorted(relevant_paths - selected_paths),
        "extra": sorted(selected_paths - relevant_paths),
    }


def rss_bytes() -> int:
    """Current resident set size, not the process lifetime high-water mark."""
    if sys.platform == "win32":
        counters = _WindowsProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not _get_process_memory_info(
            _kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.WorkingSetSize)

    statm = "/proc/self/statm"
    if os.path.exists(statm):
        with open(statm, encoding="ascii") as record:
            resident_pages = int(record.read().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE")

    # macOS has no procfs. `ru_maxrss` is a high-water mark there, so it is intentionally not
    # presented as current RSS; callers can still measure Python allocations on unsupported hosts.
    raise OSError("current RSS is unsupported on this platform")


class RssSampler:
    """Sample RSS in a background thread while an operation runs."""

    def __init__(self, interval_seconds: float = 0.01) -> None:
        self.interval_seconds = interval_seconds
        self.peak_bytes: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Self:
        try:
            self.peak_bytes = rss_bytes()
        except OSError:
            return self
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()
        return self

    def _sample(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.peak_bytes = max(self.peak_bytes or 0, rss_bytes())
            except OSError:
                return

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        try:
            self.peak_bytes = max(self.peak_bytes or 0, rss_bytes())
        except OSError:
            pass
