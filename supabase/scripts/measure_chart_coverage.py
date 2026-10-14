"""Local chart line coverage using stdlib trace; no secrets or hosted connections."""

import json
import os
import sys
import trace
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import pytest


class ChartTrace(trace.Trace):
    def __init__(self, source):
        super().__init__(count=True, trace=False)
        prefix = os.path.normcase(str(source / "chart_"))
        self.allowed = lru_cache(maxsize=None)(
            lambda name: os.path.normcase(name).startswith(prefix)
        )

    def globaltrace_lt(self, frame, why, arg):
        if why == "call" and self.allowed(frame.f_code.co_filename):
            return self.localtrace
        return None


def main():
    root = Path(__file__).resolve().parents[2]
    source = root / "scanner/src/idx_scanner"
    modules = tuple(sorted(source.glob("chart_*.py")))
    tests = tuple(sorted((root / "scanner/tests").glob("test_chart_*.py")))
    temporary = (root / "data/chart-test-temp" / ("coverage-" + uuid4().hex)).resolve()
    if root.resolve() not in temporary.parents:
        raise RuntimeError("invalid_local_test_directory")
    temporary.mkdir(parents=True)
    tracer = ChartTrace(source)
    status = tracer.runfunc(
        pytest.main,
        [str(p) for p in tests]
        + [
            "-q",
            "--tb=short",
            "--basetemp",
            str(temporary),
        ],
    )
    counts = tracer.results().counts
    executed_by_file = {}
    for (name, line), count in counts.items():
        if count:
            executed_by_file.setdefault(os.path.normcase(name), set()).add(line)
    rows = []
    for module in modules:
        executable = set(trace._find_executable_linenos(str(module)))
        executed = executed_by_file.get(os.path.normcase(str(module)), set())
        covered = len(executable & executed)
        rows.append(
            {
                "module": module.name,
                "covered": covered,
                "statements": len(executable),
                "percent": round(100 * covered / max(1, len(executable)), 2),
                "missing_lines": sorted(executable - executed),
            }
        )
    total = sum(row["statements"] for row in rows)
    percent = round(100 * sum(row["covered"] for row in rows) / max(1, total), 2)
    print(
        json.dumps(
            {"method": "stdlib-trace-executable-lines", "percent": percent, "modules": rows},
            indent=2,
        )
    )
    return status or int(not rows or any(row["percent"] < 80 for row in rows))


if __name__ == "__main__":
    sys.exit(main())
