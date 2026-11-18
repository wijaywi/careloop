import csv
import json
import tempfile
import unittest
from pathlib import Path

from careloop.loop_engine import CareLoopLedger, LoopStatus
from careloop.simulator import SimulationConfig, Simulator, load_parameters
from careloop.simulator.params import validate_parameter_document
from careloop.simulator.cli import main


class SimulatorTests(unittest.TestCase):
    def test_loop_engine_is_available_to_simulator(self):
        self.assertTrue(CareLoopLedger)
        self.assertEqual(LoopStatus.CLOSED.value, "closed")

    def test_default_run_is_deterministic_and_paired(self):
        config = SimulationConfig(cohort_size=16, runs=2, seed=42)
        first = Simulator(config).run().to_dict()
        second = Simulator(config).run().to_dict()
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["arms"]["Arm A"]["n"], 32)
        self.assertEqual(first["summary"]["arms"]["B-full"]["n"], 32)
        self.assertNotIn("baseline", first["summary"]["arms"])
        self.assertNotIn("careloop", first["summary"]["arms"])
        self.assertEqual(len(first["paired_differences"]), 2)
        self.assertTrue({row["segment"] for row in first["segment_metrics"]} - {"all"})

    def test_metrics_cover_times_resolution_ownership_teachback_and_load(self):
        params = load_parameters()
        params.update({
            "cohort_size": 12,
            "runs": 1,
            "capacity.providers": {"intake": 1, "owner": 1, "specialist": 1, "clinic": 1, "manager": 1},
        })
        result = Simulator(SimulationConfig(cohort_size=12, runs=1, seed=7), params).run().to_dict()
        row = next(row for row in result["segment_metrics"] if row["segment"] == "all" and row["arm"] == "Arm A")
        for key in ("notification_time_mean", "confirmation_time_mean", "consult_time_mean", "treatment_time_mean",
                    "unresolved_30", "unresolved_60", "unresolved_90", "closure_rate", "owner_coverage_rate",
                    "teach_back_rate", "escalations", "backlog_events", "max_backlog"):
            self.assertIn(key, row)
        self.assertGreater(row["max_backlog"], 0)

    def test_cli_writes_json_and_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "result.json"
            csv_path = Path(directory) / "result.csv"
            self.assertEqual(main(["--cohort-size", "4", "--runs", "1", "--json", str(json_path), "--csv", str(csv_path)]), 0)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIn("paired_differences", payload)
            self.assertEqual(set(payload["summary"]["arms"]), {
                "Arm A", "B-full", "B_without_closure_gate", "B_without_absence_detector",
                "B_without_positive_handoff", "B_without_multilingual_passport",
            })
            self.assertNotIn("baseline", json_path.read_text(encoding="utf-8"))
            self.assertNotIn("careloop", json_path.read_text(encoding="utf-8"))
            with csv_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(rows)
            self.assertIn("row_type", rows[0])
            self.assertNotIn("baseline", csv_path.read_text(encoding="utf-8"))
            self.assertNotIn("careloop", csv_path.read_text(encoding="utf-8"))

    def test_full_defaults_and_schema_provenance(self):
        self.assertEqual(SimulationConfig().cohort_size, 10000)
        self.assertEqual(SimulationConfig().runs, 500)
        parameters = load_parameters()
        self.assertEqual(len(parameters), len(set(parameters)))
        document = {"status": "ASSUMPTION", "source": None,
                    "records": [{"name": key, "value": value, "status": "ASSUMPTION", "source": None}
                                for key, value in parameters.items()]}
        self.assertEqual(len(validate_parameter_document(document)), len(parameters))
        with self.assertRaises(ValueError):
            validate_parameter_document({"status": "ASSUMPTION", "source": None, "records": [
                {"name": "bad", "value": 1, "status": "OBSERVED", "source": "paper"}]})

    def test_zero_effect_b_full_does_not_beat_arm_a(self):
        parameters = load_parameters()
        parameters.update({
            "b_full.notification_delay_multiplier": 1.0,
            "b_full.confirmation_delay_multiplier": 1.0,
            "b_full.consult_delay_multiplier": 1.0,
            "b_full.treatment_delay_multiplier": 1.0,
            "b_full.confirmation_probability_add": 0.0,
            "b_full.consult_probability_add": 0.0,
            "b_full.treatment_probability_add": 0.0,
            "b_full.teach_back_probability_add": 0.0,
            "b_full.owner_coverage_probability_add": 0.0,
            "b_full.escalation_multiplier": 1.0,
            "b_full.cross_provider_probability_add": 0.0,
            "b_full.loss_to_follow_up_probability_add": 0.0,
            "b_full.no_show_probability_add": 0.0,
            "b_full.unnecessary_escalation_probability": 0.0,
            "b_full.result_flag_probability_add": 0.0,
        })
        result = Simulator(SimulationConfig(cohort_size=40, runs=2, seed=9), parameters).run().to_dict()
        self.assertEqual(result["summary"]["arms"]["Arm A"], result["summary"]["arms"]["B-full"])

    def test_analysis_sections_are_deterministic_and_cover_pathways(self):
        config = SimulationConfig(cohort_size=18, runs=2, seed=4)
        first = Simulator(config).run(include_sensitivity=True, include_stress=True).to_dict()
        second = Simulator(config).run(include_sensitivity=True, include_stress=True).to_dict()
        self.assertEqual(first, second)
        self.assertEqual(set(first["pathway_metrics"]), {"colorectal", "mammogram", "lab"})
        self.assertEqual(set(first["stress"]), {"few_navigators", "poor_contact_data", "cross_provider_dominant", "high_no_show"})
        self.assertTrue(first["sensitivity"]["one_at_a_time"])
        self.assertEqual(len(first["sensitivity"]["latin_hypercube"]), 8)
        self.assertIn("lower", first["intervals"]["arms"]["Arm A"]["closure_rate"])


if __name__ == "__main__":
    unittest.main()
