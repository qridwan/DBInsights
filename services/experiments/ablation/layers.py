"""Evidence layers and the ablation configurations, declared as data.

A configuration is nothing but the set of layers it may use. There is one pipeline; it reads
the set and switches layers on. Adding a configuration means adding a row here, not a code path.

Layer semantics
---------------
static_orm  ORM-aware analysis of application source (packages/core rules).
sql         Static analysis of SQL text (analyzers/sql).
declared    schema.prisma: given to the static analyzer (index coverage, model names) and to the
            correlation engine.
actual      The live database's schema (information_schema / pg_catalog). With `declared` it
            yields divergence findings; it is also what the correlation engine checks indexes
            and foreign keys against. Never merged with `declared`.
runtime     Per-request query behaviour from the collector.
data        Statistical profiling of the live data: anomaly detection against a learned
            baseline, and referential integrity.
"""

from dataclasses import dataclass
from enum import StrEnum


class Layer(StrEnum):
    STATIC_ORM = "static_orm"
    SQL = "sql"
    DECLARED = "declared"
    ACTUAL = "actual"
    RUNTIME = "runtime"
    DATA = "data"


#: Order in which layers are executed. Cheap, connection-free layers first, so that detection
#: latency reflects what each layer costs to obtain.
EXECUTION_ORDER = (
    Layer.STATIC_ORM,
    Layer.SQL,
    Layer.DECLARED,
    Layer.ACTUAL,
    Layer.RUNTIME,
    Layer.DATA,
)


@dataclass(frozen=True)
class Configuration:
    name: str
    layers: frozenset[Layer]
    description: str
    #: Sensitivity arms answer "what if the baseline were given more?" and are reported
    #: separately from the six configurations of the ablation.
    sensitivity: bool = False
    #: Where the SQL layer gets its statements: text in the repository, or statements captured
    #: from a running application (see analyzers.sql.analysis).
    sql_source: str = "repository"

    def uses(self, layer: Layer) -> bool:
        return layer in self.layers

    def ordered_layers(self) -> list[Layer]:
        return [layer for layer in EXECUTION_ORDER if layer in self.layers]


def _config(name: str, *layers: Layer, description: str, **kw: object) -> Configuration:
    return Configuration(name=name, layers=frozenset(layers), description=description, **kw)  # type: ignore[arg-type]


L = Layer
CONFIGURATIONS: dict[str, Configuration] = {
    c.name: c
    for c in (
        _config(
            "A",
            L.SQL,
            description="Static SQL analysis alone: no ORM source, no schema, no database",
        ),
        _config("B1", L.STATIC_ORM, L.SQL, description="ORM-aware source analysis, no schema"),
        _config(
            "B2",
            L.STATIC_ORM,
            L.SQL,
            L.DECLARED,
            description="+ the declared schema (schema.prisma)",
        ),
        _config(
            "C1",
            L.STATIC_ORM,
            L.SQL,
            L.DECLARED,
            L.ACTUAL,
            description="+ the live database's schema",
        ),
        _config(
            "C2",
            L.STATIC_ORM,
            L.SQL,
            L.DECLARED,
            L.ACTUAL,
            L.RUNTIME,
            description="+ runtime behaviour",
        ),
        _config(
            "C3",
            L.STATIC_ORM,
            L.SQL,
            L.DECLARED,
            L.ACTUAL,
            L.RUNTIME,
            L.DATA,
            description="+ data-quality statistics: the full hybrid",
        ),
        # Sensitivity arm, not one of the six: the SQL baseline given the statements the
        # application actually issues (as a query log would supply them), text only.
        _config(
            "A-log",
            L.SQL,
            description="Static SQL analysis over the application's captured SQL",
            sensitivity=True,
            sql_source="captured",
        ),
    )
}

ABLATION = tuple(name for name, c in CONFIGURATIONS.items() if not c.sensitivity)
SENSITIVITY = tuple(name for name, c in CONFIGURATIONS.items() if c.sensitivity)
