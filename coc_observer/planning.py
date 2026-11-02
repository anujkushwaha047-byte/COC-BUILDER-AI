"""Confidence-gated upgrade ranking and village-local resource allocation."""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .models import Reading

DEFAULT_CATEGORY_WEIGHTS = {
    "defense": 100.0,
    "resource": 85.0,
    "army": 80.0,
    "laboratory": 80.0,
    "hero": 70.0,
    "wall": 55.0,
    "other": 40.0,
}


@dataclass
class UpgradeCandidate:
    name: str
    category: str
    current_level: Optional[int] = None
    next_level: Optional[int] = None
    max_level: Optional[int] = None
    strategic_importance: Optional[float] = None
    upgrade_cost: Optional[int] = None
    currency: Optional[str] = None
    duration_hours: Optional[float] = None
    confidence: float = 0.0
    village: str = "home"


def rank_upgrades(
    candidates: Iterable[UpgradeCandidate],
    resources: Dict[str, Reading],
    available_builders: Optional[int],
    preferences: Optional[Dict[str, float]] = None,
    confidence_threshold: float = 0.65,
) -> List[dict]:
    """Rank observed candidates and reserve at most one slot per free builder."""
    weights = dict(DEFAULT_CATEGORY_WEIGHTS)
    if preferences:
        weights.update(preferences)

    ranked = []
    for candidate in candidates:
        if candidate.confidence < confidence_threshold:
            continue
        if candidate.next_level is None or candidate.next_level <= 0:
            continue

        components = [weights.get(candidate.category, weights["other"])]
        if candidate.strategic_importance is not None:
            components.append(max(0.0, min(100.0, candidate.strategic_importance)))
        if candidate.current_level is not None and candidate.max_level:
            advancement = candidate.next_level / candidate.max_level
            components.append(max(0.0, min(100.0, advancement * 100)))
        if candidate.duration_hours is not None and candidate.duration_hours >= 0:
            components.append(max(0.0, 100.0 / (1.0 + candidate.duration_hours / 24)))

        resource = resources.get(candidate.currency or "")
        resource_known = resource is not None and resource.value is not None and resource.confidence >= confidence_threshold
        if candidate.upgrade_cost is not None and candidate.upgrade_cost >= 0 and resource_known:
            affordable = resource.value >= candidate.upgrade_cost
            components.append(100.0 if affordable else 0.0)
            remaining = max(0, candidate.upgrade_cost - resource.value)
        else:
            affordable = None
            remaining = None

        ranked.append({
            "name": candidate.name,
            "village": candidate.village,
            "category": candidate.category,
            "current_level": candidate.current_level,
            "next_level": candidate.next_level,
            "score": round(sum(components) / len(components), 2),
            "confidence": candidate.confidence,
            "currency": candidate.currency,
            "upgrade_cost": candidate.upgrade_cost,
            "duration_hours": candidate.duration_hours,
            "affordable": affordable,
            "resource_shortfall": remaining,
            "status": "queued",
        })

    ranked.sort(key=lambda item: (-item["score"], item["name"].casefold()))
    builders_used = 0
    for item in ranked:
        if available_builders is None:
            item["status"] = "builder_count_unknown"
        elif available_builders <= builders_used:
            item["status"] = "waiting_for_builder"
        elif item["affordable"] is False:
            item["status"] = "waiting_for_resources"
        elif item["affordable"] is None:
            item["status"] = "cost_or_resource_unknown"
        else:
            item["status"] = "ready"
            builders_used += 1
    return ranked


def allocate_resources(
    village: str,
    resources: Dict[str, Reading],
    queue: Iterable[dict],
    wall_currency: str = "gold",
    wall_count: int = 0,
    wall_cost_each: Optional[int] = None,
) -> dict:
    """Calculate deficits using only the explicitly named village's balances."""
    allocations = []
    for upgrade in queue:
        currency = upgrade.get("currency")
        balance = resources.get(currency) if currency else None
        known = balance is not None and balance.value is not None and balance.confidence >= 0.65
        cost = upgrade.get("upgrade_cost")
        allocations.append({
            "name": upgrade.get("name", "Unknown upgrade"),
            "currency": currency,
            "required": cost,
            "available": balance.value if known else None,
            "shortfall": max(0, cost - balance.value) if known and isinstance(cost, int) else None,
            "village": village,
        })
    wall_balance = resources.get(wall_currency)
    wall_known = wall_balance is not None and wall_balance.value is not None and wall_balance.confidence >= 0.65
    wall_budget = wall_count * wall_cost_each if wall_cost_each is not None else None
    return {
        "village": village,
        "upgrades": allocations,
        "walls": {
            "count": wall_count,
            "currency": wall_currency,
            "cost_each": wall_cost_each,
            "total_required": wall_budget,
            "available": wall_balance.value if wall_known else None,
            "shortfall": max(0, wall_budget - wall_balance.value)
            if wall_known and wall_budget is not None else None,
        },
    }
