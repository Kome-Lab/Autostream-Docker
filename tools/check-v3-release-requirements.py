#!/usr/bin/env python3
"""Read-only Docker consumer of Updater's one canonical WS6 evaluator.

No Docker Engine, registry, credentials, manifest generation or release workflow
is invoked. The caller must identify the exact local evaluator executable.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

PROFILE = "IU-WS6-01/RELEASE-RETURN/1"
CONTRACTS_COMMIT = "d32ea3514b1c1010391caae0348b0ff9e751f447"
STATUS_KIND = {"StructurallyCoherent": "STRUCTURALLY_COHERENT",
               "NeedsEvidence": "NEEDS_EVIDENCE", "NeedsDecision": "NEEDS_DECISION",
               "Contradiction": "CONFLICT"}


class RedactedParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, "release_requirements_arguments_invalid\n")


def strict_json(data):
    def pairs(items):
        out, keys = {}, set()
        for key, value in items:
            if key.lower() in keys:
                raise ValueError("duplicate_json_key")
            keys.add(key.lower())
            out[key] = value
        return out
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_json")))


class Evaluator:
    def __init__(self, executable, digest, source_commit):
        self.executable = pathlib.Path(executable).resolve(strict=True)
        if not self.executable.is_file() or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("explicit_evaluator_identity_required")
        if hashlib.sha256(self.executable.read_bytes()).hexdigest() != digest:
            raise ValueError("evaluator_digest_mismatch")
        if not re.fullmatch(r"[a-f0-9]{40}", source_commit):
            raise ValueError("explicit_updater_commit_required")
        self.source_commit = source_commit
        contract = self._invoke(["--describe"], b"")
        if contract != {"profile": PROFILE, "contracts_commit": CONTRACTS_COMMIT,
                        "authorizes_mutation": False, "reusable_for_commit": False,
                        "production_qualified": False}:
            raise ValueError("evaluator_contract_mismatch")

    def _invoke(self, args, data):
        result = subprocess.run([str(self.executable), *args], input=data,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=False, timeout=30, shell=False)
        if result.returncode != 0 or len(result.stdout) > 2 * 1024 * 1024:
            raise ValueError("canonical_evaluation_unavailable")
        return strict_json(result.stdout)

    def evaluate(self, descriptor, max_bytes, max_depth):
        if max_bytes <= 0 or max_depth <= 0:
            raise ValueError("explicit_transport_budgets_required")
        data = json.dumps(descriptor, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(data) > max_bytes:
            raise ValueError("descriptor_budget_exceeded")
        result = self._invoke(["--max-input-bytes", str(max_bytes), "--max-depth", str(max_depth)], data)
        if result.get("profile") != PROFILE or result.get("contracts_commit") != CONTRACTS_COMMIT:
            raise ValueError("result_profile_mismatch")
        if result.get("status") not in STATUS_KIND or result.get("return_scenario") not in {
                "RET-S1", "RET-S2", "RET-S3", "RET-S4", "RET-S5"}:
            raise ValueError("unknown_result_enum")
        if result.get("contract_result", {}).get("Kind") != STATUS_KIND[result["status"]]:
            raise ValueError("shared_result_kind_mismatch")
        for field in ("authorizes_mutation", "reusable_for_commit", "production_qualified",
                      "common_restore_freshness_proven"):
            if result.get(field) is not False:
                raise ValueError("structural_result_cannot_authorize")
        return result


def main():
    parser = RedactedParser(description=__doc__)
    parser.add_argument("descriptor", type=pathlib.Path)
    parser.add_argument("--evaluator", required=True)
    parser.add_argument("--evaluator-sha256", required=True)
    parser.add_argument("--updater-commit", required=True)
    parser.add_argument("--max-input-bytes", required=True, type=int)
    parser.add_argument("--max-depth", required=True, type=int)
    args = parser.parse_args()
    try:
        if args.max_input_bytes <= 0 or args.descriptor.stat().st_size > args.max_input_bytes:
            raise ValueError("descriptor_budget_exceeded")
        descriptor = strict_json(args.descriptor.read_bytes())
        evaluator = Evaluator(args.evaluator, args.evaluator_sha256, args.updater_commit)
        result = evaluator.evaluate(descriptor, args.max_input_bytes, args.max_depth)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError):
        # Do not echo descriptor text, paths, URLs, payload or provider diagnostics.
        print("release_requirements_check_unavailable", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
