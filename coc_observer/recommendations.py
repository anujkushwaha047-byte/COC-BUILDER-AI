"""Deterministic, confidence-gated upgrade planning."""

from typing import Dict, List

from .models import Observation

HAMMER_JAM_DISCOUNT = 0.50


def recommend(observation: Observation) -> List[dict]:
    recommendations = []
    if not observation.buildings:
        return recommendations
    resource_values = {
        name: reading.value
        for name, reading in observation.resources.items()
        if reading.value is not None and reading.confidence >= 0.75
    }
    priorities = {
        "defense": 1,
        "resource": 2,
        "army": 3,
        "laboratory": 3,
        "hero": 4,
        "other": 5,
    }
    for building in observation.buildings:
        if building.get("confidence", 0) < 0.75:
            continue
        category = building.get("category", "other")
        recommendation = {
            "name": building["name"],
            "category": category,
            "priority": priorities.get(category, priorities["other"]),
            "reason": "Priority follows the configured village progression order.",
        }
        cost = building.get("upgrade_cost")
        currency = building.get("currency")
        if isinstance(cost, int) and currency in resource_values:
            discounted = int(cost * (1 - HAMMER_JAM_DISCOUNT))
            recommendation.update({
                "normal_cost": cost,
                "hammer_jam_cost": discounted,
                "savings": cost - discounted,
                "affordable": resource_values[currency] >= discounted,
            })
        else:
            recommendation["affordable"] = None
        recommendations.append(recommendation)
    return sorted(recommendations, key=lambda item: (item["priority"], item["name"]))
