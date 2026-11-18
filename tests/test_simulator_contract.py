"""Focused Revision 2 simulator contract tests."""

import json
import csv
import re
import tempfile
import unittest
from pathlib import Path

from careloop.simulator import SimulationConfig, Simulator, load_parameters
from careloop.simulator.cli import main


class SimulatorV2Tests(unittest.TestCase):
    def small(self, **overrides):
        config = SimulationConfig(cohort_size=10, runs=2, seed=91, **overrides)
        return Simulator(config).run(include_sensitivity=False, include_stress=False).to_dict()

    def test_canonical_arms_are_paired_and_reproducible(self):
        first = self.small()
        second = self.small()
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["arms"]["Arm A"]["n"], 20)
        self.assertEqual(first["summary"]["arms"]["B-full"]["n"], 20)
        self.assertEqual(len(first["paired_differences"]), 2)
        self.assertEqual(first["paired_differences"][0]["comparison"], "B-full_minus_Arm_A")
        self.assertNotIn("baseline", first["summary"]["arms"])
        self.assertNotIn("careloop", first["summary"]["arms"])
        self.assertIn("B_without_closure_gate", first["ablations"]["arms"])

    def test_revision_two_outputs_cover_closure_evidence_leakage_and_owner(self):
        result = self.small()
        arm = result["summary"]["arms"]["B-full"]
        for key in ("uncertainty_hours", "unknown_rate", "evidence_rate",
                    "consult_without_referral_rate", "closure_within_sla_rate",
                    "owner", "core_metric"):
            self.assertIn(key, arm)
        self.assertEqual(arm["core_metric"], "named_owner_and_documented_closure_within_sla")
        self.assertTrue(result["leakage_map"])
        self.assertEqual({row["stage"] for row in result["leakage_map"]}, set(range(1, 12)))
        self.assertIn("fifo", result["workload"]["arms"])
        self.assertIn("priority", result["workload"]["arms"])

    def test_switching_an_ablation_changes_event_mechanics(self):
        params = load_parameters()
        params.update({
            "arm_a.no_show_probability": 0.3,
            "b_full.no_show_probability_add": 0.0,
            "closure_evidence_probability": 0.35,
        })
        result = Simulator(SimulationConfig(cohort_size=30, runs=1, seed=17), params).run().to_dict()
        full = result["summary"]["arms"]["B-full"]
        no_absence = result["summary"]["arms"]["B_without_absence_detector"]
        no_gate = result["summary"]["arms"]["B_without_closure_gate"]
        self.assertNotEqual(full["patient_pull_rate"], no_absence["patient_pull_rate"])
        self.assertNotEqual(full["closure_rate"], no_gate["closure_rate"])

    def test_stress_scenarios_and_parameter_registry_are_explicit(self):
        result = Simulator(SimulationConfig(cohort_size=6, runs=1, seed=3)).run(include_stress=True).to_dict()
        self.assertEqual(set(result["stress_scenarios"]), {
            "insufficient_staff", "poor_contact_data", "cross_provider_dominant",
            "rare_reporting", "e_consult_unavailable",
        })
        records = result["parameters"]["records"]
        self.assertTrue(all(record["status"] == "assumption" for record in records))
        self.assertTrue(all(record["source"] == "not yet found / assumption" for record in records))
        registry_path = Path(__file__).parents[1] / "careloop" / "simulator" / "params" / "registry.csv"
        with registry_path.open(newline="", encoding="utf-8") as handle:
            registry = list(csv.DictReader(handle))
        self.assertEqual(set(registry[0]), {"parameter", "value_range", "distribution", "source", "status", "notes"})
        self.assertEqual(len(registry), len(records))
        self.assertTrue(all(row["source"] == "not yet found / assumption" for row in registry))
        sla_path = registry_path.parent / "sla_policy.json"
        sla = json.loads(sla_path.read_text(encoding="utf-8"))
        self.assertEqual(sla["status"], "assumption")
        self.assertEqual(sla["source"], "not yet found / assumption")
        self.assertEqual(len(sla["stages"]), 10)
        self.assertTrue(all({"owner", "escalate_to", "expected_event", "urgent_hours", "routine_hours"}.issubset(row) for row in sla["stages"]))
        self.assertEqual(sla["primary_screening_type"], "breast_cancer_abnormal_mammogram")
        stage9 = next(row for row in sla["stages"] if row["stage"] == 9)
        self.assertEqual(stage9["urgent_hours"], 336)
        self.assertEqual(stage9["routine_hours"], 720)

    def test_cli_module_switch_is_applied_to_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "modules.json"
            self.assertEqual(main(["--bounded", "--cohort-size", "4", "--runs", "1",
                                   "--disable-module", "multilingual_passport", "--json", str(path)]), 0)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(payload["config"]["modules"]["multilingual_passport"])

    def test_bounded_cli_caps_explicit_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bounded.json"
            self.assertEqual(main(["--bounded", "--cohort-size", "99", "--runs", "99",
                                   "--max-cohort-size", "3", "--max-runs", "2",
                                   "--json", str(path)]), 0)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["config"]["cohort_size"], 3)
            self.assertEqual(payload["config"]["runs"], 2)
            self.assertTrue(payload["config"]["bounded"])

    def test_default_language_is_english_and_registry_defaults_are_in_range(self):
        parameters = load_parameters()
        self.assertEqual(parameters["segment_weights.language"], {"English": 1.0})
        registry_path = Path(__file__).parents[1] / "careloop" / "simulator" / "params" / "registry.csv"
        with registry_path.open(newline="", encoding="utf-8") as handle:
            registry = {row["parameter"]: row for row in csv.DictReader(handle)}
        manifest = json.loads((registry_path.parent / "default.yml").read_text(encoding="utf-8"))
        for record in manifest["records"]:
            value = record.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            value_range = registry[record["name"]]["value_range"]
            match = re.fullmatch(r"(?:\[|)([-+]?\d+(?:\.\d+)?)\.\.(?:|\[)([-+]?\d+(?:\.\d+)?)(?:\]|)", value_range)
            if not match:
                match = re.fullmatch(r"\[\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*\]", value_range)
            self.assertIsNotNone(match, record["name"])
            low, high = map(float, match.groups())
            self.assertGreaterEqual(float(value), low, record["name"])
            self.assertLessEqual(float(value), high, record["name"])

    def test_stress_overrides_are_applied_to_the_requested_scenario(self):
        result = Simulator(SimulationConfig(cohort_size=40, runs=2, seed=11)).run(include_stress=True).to_dict()
        stress = result["stress_scenarios"]["poor_contact_data"]
        self.assertEqual(stress["parameters"]["contact_data_quality"], 0.45)
        self.assertIn("Arm A", stress["summary"]["arms"])
        self.assertIn("B-full", stress["summary"]["arms"])


if __name__ == "__main__":
    unittest.main()
