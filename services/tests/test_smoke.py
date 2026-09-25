import importlib

import pytest


@pytest.mark.parametrize("module", ["api", "analyzers", "experiments"])
def test_packages_import(module: str) -> None:
    importlib.import_module(module)
