"""Editable daily mission defaults and date-scoped progress."""

from dataclasses import asdict, dataclass
from datetime import date
from typing import Dict, Optional


@dataclass
class MissionSettings:
    wall_upgrades: int = 325
    defense_upgrades: int = 28
    army_upgrades_enabled: bool = True
    home_attacks: int = 50
    builder_base_attacks: int = 30
    loot_preference: str = "maximum"
    priority_weights: Dict[str, float] = None

    def validate(self) -> None:
        for field in ("wall_upgrades", "defense_upgrades", "home_attacks", "builder_base_attacks"):
            value = getattr(self, field)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be a non-negative integer")
        if self.loot_preference not in {"maximum", "balanced", "dark_elixir"}:
            raise ValueError("loot_preference must be maximum, balanced, or dark_elixir")
        if self.priority_weights is not None:
            for category, weight in self.priority_weights.items():
                if not isinstance(weight, (int, float)) or not 0 <= weight <= 100:
                    raise ValueError(f"priority weight for {category} must be between 0 and 100")

    def to_dict(self) -> dict:
        self.validate()
        return asdict(self)


def default_mission_settings() -> MissionSettings:
    return MissionSettings()


def empty_daily_progress(day: Optional[str] = None) -> dict:
    return {
        "date": day or date.today().isoformat(),
        "home_attacks": 0,
        "builder_base_attacks": 0,
        "wall_upgrades": 0,
        "defense_upgrades": 0,
        "army_upgrades": 0,
    }


def mission_summary(settings: MissionSettings, progress: dict) -> dict:
    settings.validate()
    targets = settings.to_dict()
    return {
        key: {
            "target": targets[key],
            "completed": progress.get(key, 0),
            "remaining": max(0, targets[key] - progress.get(key, 0)),
            "complete": progress.get(key, 0) >= targets[key],
        }
        for key in ("wall_upgrades", "defense_upgrades", "home_attacks", "builder_base_attacks")
    }
