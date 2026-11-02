from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class Reading:
    value: Optional[object] = None
    confidence: float = 0.0
    source: str = "not observed"


@dataclass
class Observation:
    observed_at: str
    screen_width: int
    screen_height: int
    resources: Dict[str, Reading] = field(default_factory=dict)
    town_hall_level: Reading = field(default_factory=Reading)
    builders_available: Reading = field(default_factory=Reading)
    builders_total: Reading = field(default_factory=Reading)
    active_upgrades: List[dict] = field(default_factory=list)
    buildings: List[dict] = field(default_factory=list)
    obstacles: List[dict] = field(default_factory=list)
    collection_indicators: List[dict] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    ocr_available: bool = False

    @classmethod
    def empty(cls, width: int = 0, height: int = 0) -> "Observation":
        return cls(
            observed_at=datetime.now(timezone.utc).isoformat(),
            screen_width=width,
            screen_height=height,
            resources={name: Reading() for name in ("gold", "elixir", "dark_elixir", "gems")},
        )
