"""Village status interpretation that preserves low-confidence and missing data."""

from typing import Dict, List

from .models import Observation


def analyze(observation: Observation) -> Dict[str, object]:
    known_resources = {
        name: reading.value
        for name, reading in observation.resources.items()
        if reading.value is not None and reading.confidence >= 0.65
    }
    builders_idle = observation.builders_available.value == observation.builders_total.value \
        and observation.builders_available.value is not None \
        and observation.builders_available.confidence >= 0.65
    return {
        "known_resources": known_resources,
        "idle_builders": builders_idle,
        "upgrade_count": len(observation.active_upgrades),
        "building_count": len(observation.buildings),
        "completion_percentage": None,
        "completion_note": "Unavailable until building identities and levels are reliably observed.",
    }
