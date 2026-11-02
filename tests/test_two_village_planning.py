import tempfile
import unittest
from pathlib import Path

from coc_observer.farming import LootOpportunity, analyze_opportunity
from coc_observer.missions import MissionSettings, empty_daily_progress, mission_summary
from coc_observer.models import Reading
from coc_observer.planning import UpgradeCandidate, allocate_resources, rank_upgrades
from coc_observer.storage import ObservationStore


class TwoVillagePlanningTests(unittest.TestCase):
    def test_upgrade_queue_respects_builder_count_and_unknown_inputs(self):
        candidates = [
            UpgradeCandidate(
                name="Archer Tower", category="defense", current_level=10,
                next_level=11, max_level=20, upgrade_cost=100, currency="gold",
                duration_hours=24, confidence=0.95,
            ),
            UpgradeCandidate(
                name="Barracks", category="army", current_level=5,
                next_level=6, max_level=10, upgrade_cost=50, currency="elixir",
                confidence=0.95,
            ),
        ]
        queue = rank_upgrades(
            candidates,
            {"gold": Reading(200, 0.9), "elixir": Reading(200, 0.9)},
            available_builders=1,
        )
        self.assertEqual(1, sum(item["status"] == "ready" for item in queue))
        unknown = rank_upgrades(candidates, {}, available_builders=None)
        self.assertTrue(all(item["status"] == "builder_count_unknown" for item in unknown))

    def test_resource_allocation_keeps_village_balances_separate(self):
        home_resources = {"gold": Reading(500, 0.9)}
        builder_resources = {"gold": Reading(25, 0.9)}
        upgrade = {"name": "Cannon", "currency": "gold", "upgrade_cost": 100}
        home = allocate_resources("home", home_resources, [upgrade])
        builder = allocate_resources("builder_base", builder_resources, [upgrade])
        self.assertEqual(0, home["upgrades"][0]["shortfall"])
        self.assertEqual(75, builder["upgrades"][0]["shortfall"])
        self.assertEqual("home", home["village"])
        self.assertEqual("builder_base", builder["village"])

    def test_mission_defaults_validation_and_daily_summary(self):
        settings = MissionSettings()
        self.assertEqual(325, settings.wall_upgrades)
        self.assertEqual(28, settings.defense_upgrades)
        self.assertEqual(50, settings.home_attacks)
        self.assertEqual(30, settings.builder_base_attacks)
        progress = empty_daily_progress("2026-11-02")
        progress["home_attacks"] = 12
        summary = mission_summary(settings, progress)
        self.assertEqual(38, summary["home_attacks"]["remaining"])
        with self.assertRaises(ValueError):
            MissionSettings(wall_upgrades=-1).validate()

    def test_loot_analysis_preserves_partial_unknowns_and_confidence(self):
        result = analyze_opportunity(LootOpportunity(
            village="home",
            gold=1000,
            elixir=None,
            dark_elixir=100,
            confidence=0.8,
            resource_confidence={"gold": 0.5, "dark_elixir": 0.9},
        ))
        self.assertEqual(500, result["confidence_adjusted_loot"]["gold"])
        self.assertIsNone(result["confidence_adjusted_loot"]["elixir"])
        self.assertEqual(90, result["confidence_adjusted_loot"]["dark_elixir"])
        self.assertEqual("unknown", result["difficulty_label"])

    def test_village_observations_and_daily_progress_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ObservationStore(Path(directory) / "data.sqlite3")
            store.save_village_observation("home", "2026-11-02T10:00:00Z", {"gold": 500})
            store.save_village_observation("builder_base", "2026-11-02T10:00:00Z", {"gold": 25})
            store.increment_daily_progress("home", "attacks", day="2026-11-02")
            store.increment_daily_progress("builder_base", "attacks", 2, day="2026-11-02")
            self.assertEqual(
                [{"gold": 500}],
                store.recent_village_observations("home"),
            )
            self.assertEqual(
                [{"gold": 25}],
                store.recent_village_observations("builder_base"),
            )
            progress = store.get_daily_progress("2026-11-02")
            self.assertEqual(1, progress["home_attacks"])
            self.assertEqual(2, progress["builder_base_attacks"])
            with self.assertRaises(ValueError):
                store.save_village_observation("unknown", "time", {})


if __name__ == "__main__":
    unittest.main()
