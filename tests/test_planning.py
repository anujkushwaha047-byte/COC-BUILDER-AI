import tempfile
import unittest
from pathlib import Path

from coc_observer.analyzer import analyze
from coc_observer.models import Observation, Reading
from coc_observer.recommendations import recommend
from coc_observer.storage import ObservationStore
from coc_observer.vision import _parse_amount


class PlanningTests(unittest.TestCase):
    def test_incomplete_observation_does_not_invent_progress(self):
        observation = Observation.empty()
        result = analyze(observation)
        self.assertIsNone(result["completion_percentage"])
        self.assertEqual([], recommend(observation))

    def test_recommendations_apply_hammer_jam_discount_and_priority(self):
        observation = Observation.empty()
        observation.resources["gold"] = Reading(100_000, 0.95, "test")
        observation.buildings = [
            {"name": "Archer Tower", "category": "defense", "confidence": 0.95,
             "upgrade_cost": 100_000, "currency": "gold"},
            {"name": "Gold Mine", "category": "resource", "confidence": 0.9,
             "upgrade_cost": 80_000, "currency": "gold"},
        ]
        result = recommend(observation)
        self.assertEqual("Archer Tower", result[0]["name"])
        self.assertEqual(50_000, result[0]["hammer_jam_cost"])
        self.assertEqual(50_000, result[0]["savings"])
        self.assertTrue(result[0]["affordable"])
        self.assertEqual(2, result[1]["priority"])

    def test_amount_parser_handles_suffixes_and_separators(self):
        self.assertEqual(1_250_000, _parse_amount("1.25M"))
        self.assertEqual(123_456, _parse_amount("123,456"))
        self.assertIsNone(_parse_amount("not a number"))

    def test_observation_round_trips_through_local_database(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ObservationStore(Path(directory) / "observations.sqlite3")
            observation = Observation.empty(1920, 1080)
            observation.resources["gold"] = Reading(42_000, 0.9, "test")
            store.save(observation)
            saved = store.recent(1)[0]
            self.assertEqual(observation.observed_at, saved["observed_at"])
            self.assertEqual(42_000, saved["resources"]["gold"]["value"])


if __name__ == "__main__":
    unittest.main()
