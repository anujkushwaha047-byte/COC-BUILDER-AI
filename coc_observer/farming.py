"""Transparent farming calculations for observed loot opportunities."""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class LootOpportunity:
    village: str
    gold: Optional[int] = None
    elixir: Optional[int] = None
    dark_elixir: Optional[int] = None
    confidence: float = 0.0
    difficulty: Optional[float] = None
    source: str = "not observed"
    resource_confidence: Optional[Dict[str, float]] = None


def analyze_opportunity(opportunity: LootOpportunity) -> dict:
    confidence = max(0.0, min(1.0, opportunity.confidence))
    amounts = (opportunity.gold, opportunity.elixir, opportunity.dark_elixir)
    loot_known = any(value is not None and value >= 0 for value in amounts)
    per_resource_confidence = opportunity.resource_confidence or {}
    values = {
        "gold": opportunity.gold,
        "elixir": opportunity.elixir,
        "dark_elixir": opportunity.dark_elixir,
    }
    estimated = {
        name: (
            int(value * max(0.0, min(1.0, per_resource_confidence.get(name, confidence))))
            if value is not None and value >= 0 else None
        )
        for name, value in values.items()
    }
    return {
        "village": opportunity.village,
        "observed_loot": {
            "gold": opportunity.gold,
            "elixir": opportunity.elixir,
            "dark_elixir": opportunity.dark_elixir,
        },
        "confidence_adjusted_loot": estimated,
        "difficulty": opportunity.difficulty,
        "difficulty_label": (
            "unknown" if opportunity.difficulty is None
            else "easy" if opportunity.difficulty < 35
            else "moderate" if opportunity.difficulty < 70
            else "hard"
        ),
        "confidence": confidence,
        "source": opportunity.source,
        "loot_preference": "maximum",
        "efficiency": None,
        "recommendation": (
            "Loot estimate unavailable; no opponent loot values were confidently observed."
            if not loot_known
            else "Some loot types are unknown; compare only observed values with your village-local resource shortfall."
            if any(value is None for value in amounts)
            else "Compare confidence-adjusted loot with your village-local resource shortfall."
        ),
    }


def recommend_attack_strategy(village: str, loot_preference: str = "maximum") -> dict:
    if village not in {"home", "builder_base"}:
        raise ValueError("village must be 'home' or 'builder_base'")
    if loot_preference not in {"maximum", "balanced", "dark_elixir"}:
        raise ValueError("unsupported loot preference")
    return {
        "village": village,
        "loot_preference": loot_preference,
        "composition": None,
        "difficulty": None,
        "recommendation": (
            "Prefer a loot-focused target and use an army composition from troops you have unlocked."
            if loot_preference == "maximum"
            else "Prefer a target matching the selected resource preference and use troops you have unlocked."
        ),
        "reason": "Troop unlocks, army capacity, opponent defenses, and target loot are not reliably observed.",
        "automated_attack": False,
    }
