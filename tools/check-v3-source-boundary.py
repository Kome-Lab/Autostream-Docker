#!/usr/bin/env python3
"""Verify exact additive WS6 source; preserve all existing Docker distribution."""
import hashlib
import json
import pathlib
import re
import subprocess

BASELINE = "5322ed42bba9e29ed39b1e5a09689ec93644c462"
MANIFEST = "tools/v3-source-patches.json"


def git(*args):
    return subprocess.check_output(["git", *args])


def canonical(data):
    return data.replace(b"\r\n", b"\n")


def main():
    manifest = json.loads(pathlib.Path(MANIFEST).read_text(encoding="utf-8"))
    assert manifest["schema"] == 1 and manifest["baseline"] == BASELINE
    assert manifest["patches"] == {}, "legacy Docker source must remain unchanged"
    owned = set(manifest["new"]) | {MANIFEST}
    assert MANIFEST not in manifest["new"], "self-referential source manifest"
    for path in owned:
        parsed = pathlib.PurePosixPath(path)
        assert not parsed.is_absolute() and ".." not in parsed.parts and "\\" not in path, "unsafe source path"
        assert parsed.suffix in {".py", ".json", ".md", ".yml", ".txt"}, "unexpected generated or executable artifact"
    changed = {}
    for line in git("diff", "--name-status", BASELINE, "HEAD").decode().splitlines():
        status, path = line.split("\t", 1)
        assert status == "A", "preserved Docker source modified/deleted/renamed: " + path
        changed[path] = status
    assert set(changed) == owned, "diff does not match exact reviewed WS6 manifest"
    git("merge-base", "--is-ancestor", BASELINE, "HEAD")
    git("diff", "--exit-code", "HEAD", "--")
    for path, expected in manifest["new"].items():
        actual = canonical(pathlib.Path(path).read_bytes())
        assert hashlib.sha256(actual).hexdigest() == expected, "new source changed: " + path
    workflow = pathlib.Path(".github/workflows/v3-release-requirements.yml").read_text(encoding="utf-8")
    assert re.search(r"^on:\n  pull_request:\n    branches: \[v3-dev\]\n", workflow, re.MULTILINE), "unexpected WS6 event"
    assert "contents: read" in workflow and "persist-credentials: false" in workflow
    assert not re.search(r"(?:\bdocker\s+(?:push|login)\b|\bgh\s+release\b|\bgit\s+push\b|action-gh-release|build-push-action|(?:contents|packages|id-token|attestations):\s*write|write-all|workflow_dispatch:|workflow_call:|continue-on-error:|\$\{\{\s*secrets\.)", workflow, re.IGNORECASE), "new CI contains publication/credentials/weakening"
    for ref in re.findall(r"^\s*(?:-\s*)?uses: ([^\s#]+)", workflow, re.MULTILINE):
        assert re.fullmatch(r"[A-Za-z0-9_./-]+@[0-9a-f]{40}", ref), "unpinned CI action"
    pinned = re.search(r"^\s+IU_WS6_UPDATER_COMMIT: '([0-9a-f]{40})'$", workflow, re.MULTILINE)
    assert pinned and pinned.group(1) == "5741d48d94f6fe7c6727f637ea32667860882dfd", "Updater source pin not finalized"
    print(git("log", "-1", "--format=WS6 tested commit: %H%nWS6 tested tree: %T").decode().strip())
    print(f"WS6 exact source boundary: PASS added={len(manifest['new'])} metadata=1; all legacy source/pins preserved")


if __name__ == "__main__":
    main()
