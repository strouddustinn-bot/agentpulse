"""Self-contained test runner so the suite runs without pip/pytest installed.

Implements the small subset of pytest the suite uses: pytest.raises,
pytest.mark.parametrize (stackable), and the tmp_path fixture. Discovers
test_* functions across tests/, expands parametrization, runs them, and exits
non-zero on any failure.
"""

import importlib.util
import inspect
import itertools
import os
import pathlib
import sys
import tempfile
import traceback
import types

# ---- fake `pytest` module --------------------------------------------------

pytest = types.ModuleType("pytest")


class _Raises:
    def __init__(self, exc):
        self.exc = exc

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"DID NOT RAISE {self.exc!r}")
        return issubclass(et, self.exc)


def _raises(exc):
    return _Raises(exc)


class _Mark:
    @staticmethod
    def parametrize(argnames, argvalues):
        def deco(fn):
            layers = list(getattr(fn, "_params", []))
            layers.append((argnames, list(argvalues)))
            fn._params = layers
            return fn
        return deco


pytest.raises = _raises
pytest.mark = _Mark()
sys.modules["pytest"] = pytest

# ---- discovery + execution -------------------------------------------------

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _expand(layer):
    names, values = layer
    if "," in names:
        keys = [n.strip() for n in names.split(",")]
        return [dict(zip(keys, v)) for v in values]
    return [{names: v} for v in values]


def _param_combos(fn):
    layers = getattr(fn, "_params", [])
    if not layers:
        return [{}]
    per_layer = [_expand(l) for l in layers]
    combos = []
    for combo in itertools.product(*per_layer):
        merged = {}
        for d in combo:
            merged.update(d)
        combos.append(merged)
    return combos


def _call(fn, kwargs):
    sig = inspect.signature(fn)
    call_kwargs = dict(kwargs)
    tmpdir = None
    if "tmp_path" in sig.parameters and "tmp_path" not in call_kwargs:
        tmpdir = tempfile.mkdtemp(prefix="aptest_")
        call_kwargs["tmp_path"] = pathlib.Path(tmpdir)
    fn(**call_kwargs)


def main():
    test_dir = ROOT / "tests"
    passed = failed = 0
    failures = []
    for path in sorted(test_dir.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name, fn in sorted(vars(mod).items()):
            if not (name.startswith("test_") and callable(fn)):
                continue
            for kwargs in _param_combos(fn):
                label = f"{path.name}::{name}"
                if kwargs:
                    label += f"[{kwargs}]"
                try:
                    _call(fn, kwargs)
                    passed += 1
                except Exception:  # noqa: BLE001 - report all
                    failed += 1
                    failures.append((label, traceback.format_exc()))
    print(f"\n{'='*60}")
    print(f"PASSED: {passed}   FAILED: {failed}")
    if failures:
        print(f"{'='*60}")
        for label, tb in failures:
            print(f"\nFAIL {label}\n{tb}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
