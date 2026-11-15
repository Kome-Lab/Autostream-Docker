"""Literal WS6 oracle through Docker consumer -> actual Updater executable."""
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("v3_requirements", ROOT / "tools/check-v3-release-requirements.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ReleaseRequirementsContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Required test configuration: absence is an error, never a skip/fallback.
        binary = pathlib.Path(os.environ["IU_WS6_EVALUATOR"])
        cls.source_commit = os.environ["IU_WS6_UPDATER_COMMIT"]
        cls.digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        cls.evaluator = checker.Evaluator(binary, cls.digest, cls.source_commit)
        cls.fixture = checker.strict_json((ROOT / "testdata/v3-release-requirements/conformance.json").read_bytes())

    def test_required_literal_vectors(self):
        fixture = self.fixture
        self.assertEqual(fixture["profile"], checker.PROFILE)
        self.assertEqual(fixture["contracts_commit"], checker.CONTRACTS_COMMIT)
        self.assertIs(fixture["test_only"], True)
        self.assertIs(fixture["production_qualified"], False)
        self.assertEqual(len(fixture["cases"]), 18)
        for case in fixture["cases"]:
            with self.subTest(case=case["id"], scenario=case["scenario"]):
                descriptor = copy.deepcopy(fixture["base"])
                for change in case["changes"]:
                    cursor = descriptor
                    for key in change["path"][:-1]:
                        cursor = cursor[key]
                    cursor[change["path"][-1]] = copy.deepcopy(change["value"])
                result = self.evaluator.evaluate(descriptor, 2 * 1024 * 1024, 64)
                self.assertEqual(result["status"], case["expected"]["status"])
                self.assertEqual(result["return_scenario"], case["expected"]["return_scenario"])
                reason = case["expected"]["reason"]
                if reason:
                    self.assertIn(reason, result["reasons"])
                for field in ("authorizes_mutation", "reusable_for_commit", "production_qualified",
                              "common_restore_freshness_proven"):
                    self.assertIs(result[field], False)

    def test_same_descriptor_bytes_as_pinned_updater(self):
        counterpart = pathlib.Path(os.environ["IU_WS6_UPDATER_SOURCE"]) / "internal/releasequalification/testdata/conformance.json"
        self.assertEqual(counterpart.read_bytes(), (ROOT / "testdata/v3-release-requirements/conformance.json").read_bytes())

    def test_no_implicit_binary_or_trust(self):
        binary = pathlib.Path(os.environ["IU_WS6_EVALUATOR"])
        with self.assertRaises(ValueError):
            checker.Evaluator(binary, "0" * 64, self.source_commit)
        with self.assertRaises(ValueError):
            checker.Evaluator(binary, self.digest, "main")
        with self.assertRaises(ValueError):
            self.evaluator.evaluate(self.fixture["base"], 0, 64)
        with self.assertRaises(ValueError):
            self.evaluator.evaluate(self.fixture["base"], 2 * 1024 * 1024, 0)

    def test_structural_does_not_qualify_runtime_or_return(self):
        result = self.evaluator.evaluate(self.fixture["base"], 2 * 1024 * 1024, 64)
        self.assertEqual(result["status"], "StructurallyCoherent")
        self.assertIs(result["production_qualified"], False)
        self.assertIs(result["authorizes_mutation"], False)
        self.assertIs(result["common_restore_freshness_proven"], False)

    def test_duplicate_or_boolean_only_never_qualifies(self):
        with self.assertRaises(ValueError):
            checker.strict_json('{"profile":"a","PROFILE":"b"}')
        with self.assertRaises(ValueError):
            self.evaluator.evaluate({"rollback_compatible": True, "backup_available": True}, 1024, 32)


if __name__ == "__main__":
    unittest.main()
