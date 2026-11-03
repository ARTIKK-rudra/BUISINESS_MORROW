from decimal import Decimal

from app.core.errors import ConflictError

UNITS: dict[str, tuple[str, Decimal]] = {
    "kg": ("mass", Decimal("1")),
    "g": ("mass", Decimal("0.001")),
    "mg": ("mass", Decimal("0.000001")),
    "lb": ("mass", Decimal("0.45359237")),
    "l": ("volume", Decimal("1")),
    "ml": ("volume", Decimal("0.001")),
    "each": ("count", Decimal("1")),
    "piece": ("count", Decimal("1")),
    "portion": ("count", Decimal("1")),
    "pack": ("count", Decimal("1")),
}


def normalize_unit(unit: str) -> str:
    normalized = unit.strip().lower()
    if normalized not in UNITS:
        raise ConflictError(f"Unsupported unit '{unit}'. Use a configured unit code")
    return normalized


def convert_quantity(quantity: Decimal, source_unit: str, target_unit: str) -> Decimal:
    source = normalize_unit(source_unit)
    target = normalize_unit(target_unit)
    source_dimension, source_factor = UNITS[source]
    target_dimension, target_factor = UNITS[target]
    if source_dimension != target_dimension:
        raise ConflictError(f"Cannot convert {source} to {target}")
    return (quantity * source_factor / target_factor).quantize(Decimal("0.001"))


def available_units() -> list[dict[str, str]]:
    return [
        {"code": code, "dimension": dimension}
        for code, (dimension, _factor) in sorted(UNITS.items())
    ]
