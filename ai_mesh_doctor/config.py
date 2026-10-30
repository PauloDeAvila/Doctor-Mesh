from dataclasses import dataclass, asdict
import math


@dataclass(frozen=True)
class InspectionConfig:
    """Distances in world Blender units, area in squared world units."""
    distance_tolerance: float = 1e-6
    area_tolerance: float = 1e-12
    max_vertices: int = 250_000
    max_region_indices: int = 512
    max_duplicate_pairs: int = 1000
    inspect_evaluated: bool = True
    max_seconds: float = 120.0

    def __post_init__(self):
        for name in ("distance_tolerance", "area_tolerance", "max_seconds"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("max_vertices", "max_region_indices", "max_duplicate_pairs"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")

    def to_dict(self):
        return asdict(self)
