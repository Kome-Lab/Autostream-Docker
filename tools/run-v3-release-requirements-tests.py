#!/usr/bin/env python3
"""Require every reviewed WS6 root with zero skips/failures; retain JSON events."""
import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Events(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = []

    def event(self, test, action):
        self.events.append({"Test": test.id().split(".")[-1], "Action": action})

    def startTest(self, test):
        self.event(test, "run")
        super().startTest(test)

    def addSuccess(self, test):
        self.event(test, "pass")
        super().addSuccess(test)

    def addSkip(self, test, reason):
        self.event(test, "skip")
        super().addSkip(test, reason)

    def addFailure(self, test, err):
        self.event(test, "fail")
        super().addFailure(test, err)

    def addError(self, test, err):
        self.event(test, "fail")
        super().addError(test, err)

    def addSubTest(self, test, subtest, err):
        self.events.append({"Test": test.id().split(".")[-1], "Subtest": str(subtest),
                            "Action": "subpass" if err is None else "fail"})
        super().addSubTest(test, subtest, err)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("explicit JSON event output required")
    spec = importlib.util.spec_from_file_location("ws6_required", ROOT / "tools/tests/test_v3_release_requirements.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    result = unittest.TextTestRunner(verbosity=2, resultclass=Events).run(suite)
    pathlib.Path(sys.argv[1]).write_text(json.dumps(result.events, indent=2) + "\n", encoding="utf-8")
    required = (ROOT / "tools/ws6-required-tests.txt").read_text().splitlines()
    for name in required:
        assert sum(e["Test"] == name and e["Action"] == "run" for e in result.events) == 1
        assert sum(e["Test"] == name and e["Action"] == "pass" for e in result.events) == 1
    assert len(required) == 5 and result.testsRun == 5
    assert sum(e["Action"] == "subpass" for e in result.events) == 18
    assert not result.skipped and not result.failures and not result.errors
    assert not any(e["Action"] in {"skip", "fail"} for e in result.events)
    print("WS6 required roots PASS roots=5 vector_subcases=18 Skip=0 Fail=0")


if __name__ == "__main__":
    main()
