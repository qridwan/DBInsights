from pathlib import Path

import pytest

from analyzers.core_bridge import CoreError, core_cli_path
from analyzers.schema.declared import load_declared_schema

FIXTURES = Path(__file__).parents[3] / "fixtures" / "schemas"

pytestmark = pytest.mark.skipif(not core_cli_path().exists(), reason="packages/core not built")


def test_declared_schema_comes_from_the_typescript_parser():
    schema = load_declared_schema(FIXTURES / "composite-index.prisma")
    event = schema.model("Event")
    assert event is not None
    assert [[f.name for f in i.fields] for i in event.indexes] == [
        ["tenantId", "seq"],
        ["kind", "createdAt"],
        ["actorId", "kind", "createdAt"],
    ]


def test_core_errors_surface_as_core_error():
    with pytest.raises(CoreError):
        load_declared_schema(FIXTURES / "does-not-exist.prisma")
