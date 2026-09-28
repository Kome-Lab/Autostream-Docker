from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/resolve-release-sources.py"
SPEC = importlib.util.spec_from_file_location("release_sources", SCRIPT)
resolver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resolver)
LOCK = json.loads((ROOT / "release/v2.0.0-source-lock.json").read_text(encoding="utf-8"))


class GitHubFixture:
    """Read-only GitHub responses; creates no Git commits, refs or tags."""
    def __init__(self, annotated=False):
        self.responses = {}
        self.calls = []
        for row in LOCK["services"]:
            base = f"/repos/{row['repository']}/git"
            sha = row["commit"]
            commit = {"type": "commit", "sha": sha, "url": resolver.API + base + "/commits/" + sha}
            self.responses[base + "/commits/" + sha] = {"sha": sha, "url": commit["url"]}
            obj = commit
            if annotated:
                for tag_sha in ("a" * 40, "b" * 40):
                    self.responses[base + "/tags/" + tag_sha] = {
                        "sha": tag_sha, "url": resolver.API + base + "/tags/" + tag_sha, "object": obj}
                    obj = {"type": "tag", "sha": tag_sha, "url": resolver.API + base + "/tags/" + tag_sha}
            self.responses[base + "/ref/tags/v2.0.0"] = {
                "ref": "refs/tags/v2.0.0", "url": resolver.API + base + "/refs/tags/v2.0.0", "object": obj}

    def read(self, path):
        self.calls.append(path)
        if path not in self.responses:
            raise resolver.SourceError("fixture tag missing: HTTP 404")
        return copy.deepcopy(self.responses[path])


class SourceLockTests(unittest.TestCase):
    def test_exact_five_sources(self):
        actual = resolver.resolve_sources(LOCK, "candidate")
        self.assertEqual(["control-panel", "discord-bot", "encoder-recorder", "observability", "worker"], list(actual))
        self.assertEqual([row["commit"] for row in LOCK["services"]], [row["commit"] for row in actual.values()])

    def test_missing_duplicate_unknown_and_extra_service(self):
        for mutation in (lambda rows: rows.pop(), lambda rows: rows.append(rows[0]),
                         lambda rows: rows.__setitem__(4, rows[0]),
                         lambda rows: rows[0].__setitem__("service", "updater")):
            with self.subTest(mutation=mutation):
                lock = copy.deepcopy(LOCK)
                mutation(lock["services"])
                with self.assertRaises(resolver.SourceError):
                    resolver.validate_lock(lock)

    def test_schema_keys_types_and_version_are_strict(self):
        mutations = [lambda lock: lock.update(extra=True), lambda lock: lock.pop("release_id"),
                     lambda lock: lock.update(schema_version=True), lambda lock: lock.update(schema_version=2),
                     lambda lock: lock.update(release_id="v2.0.1"), lambda lock: lock.update(services={}),
                     lambda lock: lock["services"][0].update(extra=True),
                     lambda lock: lock["services"][0].pop("commit"),
                     lambda lock: lock["services"][0].update(service=[])]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                lock = copy.deepcopy(LOCK)
                mutation(lock)
                with self.assertRaises(resolver.SourceError):
                    resolver.validate_lock(lock)

    def test_malformed_sha_owner_repository_path_and_version(self):
        cases = [("commit", value) for value in (None, "main", "a" * 39, "A" * 40, "a" * 40 + "\n")]
        cases += [("repository", "other/Autostream-ControlPanel"),
                  ("repository", "Kome-Lab/Autostream-Worker"),
                  ("dockerfile", "../Dockerfile"), ("dockerfile", "services/worker/Dockerfile"),
                  ("source_version", "latest")]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                lock = copy.deepcopy(LOCK)
                lock["services"][0][field] = value
                with self.assertRaises(resolver.SourceError):
                    resolver.validate_lock(lock)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(resolver.SourceError, "duplicate JSON key"):
            resolver.load_json('{"schema_version":1,"schema_version":1}')

    def test_candidate_never_reads_tags(self):
        def unavailable(_):
            self.fail("candidate must not consult any remote")
        sources = resolver.resolve_sources(LOCK, "candidate", read_json=unavailable)
        self.assertEqual(5, len(sources))

    def test_cli_candidate_works_with_no_credentials_or_tags(self):
        env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN") and not k.endswith("_INPUT")}
        result = subprocess.run([sys.executable, str(SCRIPT), "--mode", "candidate"], env=env, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(resolver.validate_lock(LOCK), json.loads(result.stdout))

    def test_owner_version_and_manual_inputs_fail_before_reads(self):
        for kwargs in ({"owner": "elsewhere"}, {"version": "v2.0.1"},
                       {"inputs": {"worker": "v1.3.1"}}, {"inputs": {"worker": "$(echo unsafe)"}},
                       {"inputs": {"unknown": "v2.0.0"}}):
            fixture = GitHubFixture()
            with self.subTest(kwargs=kwargs), self.assertRaises(resolver.SourceError):
                resolver.resolve_sources(LOCK, "publish", read_json=fixture.read, **kwargs)
            self.assertEqual([], fixture.calls)


class PublishSourceTests(unittest.TestCase):
    def test_lightweight_tags_resolve_all_five(self):
        fixture = GitHubFixture()
        actual = resolver.resolve_sources(LOCK, "publish", inputs={"worker": "v2.0.0"}, read_json=fixture.read)
        self.assertEqual(resolver.validate_lock(LOCK), actual)
        self.assertEqual(10, len(fixture.calls))

    def test_nested_annotated_tags_are_peeled_to_commit(self):
        fixture = GitHubFixture(annotated=True)
        self.assertEqual(resolver.validate_lock(LOCK), resolver.resolve_sources(LOCK, "publish", read_json=fixture.read))
        self.assertEqual(20, len(fixture.calls))

    def test_missing_tag(self):
        fixture = GitHubFixture()
        del fixture.responses[next(path for path in fixture.responses if "/ref/" in path)]
        with self.assertRaisesRegex(resolver.SourceError, "404"):
            resolver.resolve_sources(LOCK, "publish", read_json=fixture.read)

    def test_mismatched_tag_does_not_follow_new_source(self):
        fixture = GitHubFixture()
        key = next(path for path in fixture.responses if "/ref/" in path)
        obj = fixture.responses[key]["object"]
        old_sha = obj["sha"]
        obj.update(sha="c" * 40, url=obj["url"].replace(old_sha, "c" * 40))
        fixture.responses[obj["url"].removeprefix(resolver.API)] = {"sha": obj["sha"], "url": obj["url"]}
        with self.assertRaisesRegex(resolver.SourceError, "differs from locked commit"):
            resolver.resolve_sources(LOCK, "publish", read_json=fixture.read)
        self.assertEqual(old_sha, resolver.resolve_sources(LOCK, "candidate")["control-panel"]["commit"])

    def test_wrong_ref_repository_ambiguous_and_non_commit_targets(self):
        for mutation in (lambda value: [value], lambda value: dict(value, ref="refs/tags/other"),
                         lambda value: dict(value, url=value["url"].replace("Kome-Lab", "elsewhere")),
                         lambda value: dict(value, object=dict(value["object"], type="tree")),
                         lambda value: dict(value, object=dict(value["object"], url="https://example.com/object"))):
            fixture = GitHubFixture()
            key = next(path for path in fixture.responses if "/ref/" in path)
            fixture.responses[key] = mutation(fixture.responses[key])
            with self.subTest(mutation=mutation), self.assertRaises(resolver.SourceError):
                resolver.resolve_sources(LOCK, "publish", read_json=fixture.read)

    def test_annotation_cycle_and_inconsistent_object_are_rejected(self):
        for cycle in (True, False):
            fixture = GitHubFixture(annotated=True)
            key = next(path for path in fixture.responses if "/tags/" in path and "/ref/" not in path)
            if cycle:
                fixture.responses[key]["object"] = {"type": "tag", "sha": "b" * 40,
                                                    "url": resolver.API + key.replace("a" * 40, "b" * 40)}
            else:
                fixture.responses[key]["sha"] = "c" * 40
            with self.subTest(cycle=cycle), self.assertRaises(resolver.SourceError):
                resolver.resolve_sources(LOCK, "publish", read_json=fixture.read)

    def test_fifth_source_failure_emits_no_partial_cli_map(self):
        fixture = GitHubFixture()
        del fixture.responses['/repos/Kome-Lab/Autostream-Worker/git/ref/tags/v2.0.0']
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", [str(SCRIPT), "--mode", "publish"]), \
             patch.object(resolver, "read_github", fixture.read), \
             patch.dict(os.environ, {name.upper().replace('-', '_') + '_INPUT': '' for name in resolver.REPOSITORIES}), \
             redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(1, resolver.main())
        self.assertEqual("", stdout.getvalue())
        self.assertIn("404", stderr.getvalue())
        self.assertEqual(9, len(fixture.calls))


class CheckoutTests(unittest.TestCase):
    def test_head_matches_or_fails_closed(self):
        source = resolver.validate_lock(LOCK)["worker"]
        for actual, passes in ((source["commit"], True), ("d" * 40, False)):
            with self.subTest(actual=actual), patch.object(resolver.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, actual + '\n', '')):
                if passes:
                    resolver.verify_checkout(source, Path("source"))
                else:
                    with self.assertRaisesRegex(resolver.SourceError, "HEAD differs"):
                        resolver.verify_checkout(source, Path("source"))

    def test_discord_requires_initialized_recursive_gitlinks(self):
        source = resolver.validate_lock(LOCK)["discord-bot"]
        clean = ' ' + 'a' * 40 + ' third_party/discordgo/dave/libdave (v1)\n'
        nested = ' ' + 'b' * 40 + ' third_party/discordgo/dave/libdave/cpp/vcpkg (v1)\n'
        for state, passes in ((clean + nested, True), ("", False), ('-' + clean[1:], False),
                              ('+' + clean[1:], False), (clean + '-' + nested[1:], False)):
            replies = [subprocess.CompletedProcess([], 0, source["commit"] + '\n', ''),
                       subprocess.CompletedProcess([], 0, state, '')]
            with self.subTest(state=state), patch.object(resolver.subprocess, "run", side_effect=replies):
                if passes:
                    resolver.verify_checkout(source, Path("source"))
                else:
                    with self.assertRaises(resolver.SourceError):
                        resolver.verify_checkout(source, Path("source"))


class CandidateArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        workflow = (ROOT / '.github/workflows/release-candidate.yml').read_text(encoding='utf-8')
        self.program = textwrap.dedent(workflow.split("python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0])

    def write_archive(self, architecture="amd64", source_commit=None, corrupt=False, missing_layer=False):
        source = LOCK['services'][0]
        config = {'os': 'linux', 'architecture': architecture, 'config': {'Labels': {
            'org.opencontainers.image.revision': source_commit or source['commit'],
            'org.opencontainers.image.version': source['source_version'],
            'org.opencontainers.image.source': 'https://github.com/' + source['repository']}}}
        files = {'oci-layout': b'{"imageLayoutVersion":"1.0.0"}'}
        def descriptor(value):
            data = json.dumps(value, separators=(',', ':')).encode()
            sha = hashlib.sha256(data).hexdigest()
            files['blobs/sha256/' + sha] = data
            return {'digest': 'sha256:' + sha, 'size': len(data)}
        config_ref = descriptor(config)
        layer = descriptor({'fixture': 'synthetic-layer-not-a-runtime-image'})
        manifest = descriptor({'schemaVersion': 2, 'config': config_ref, 'layers': [layer]})
        files['index.json'] = json.dumps({'schemaVersion': 2, 'manifests': [manifest]}).encode()
        if corrupt:
            files['blobs/sha256/' + config_ref['digest'].split(':')[1]] = b'{}'
        if missing_layer:
            del files['blobs/sha256/' + layer['digest'].split(':')[1]]
        archive = self.output / 'image.oci.tar'
        with tarfile.open(archive, 'w') as package:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                package.addfile(info, io.BytesIO(data))
        return archive

    def execute(self):
        env = dict(os.environ, SERVICE='control-panel', PLATFORM='linux/amd64',
                   DOCKERFILES_ROOT=str(ROOT), CANDIDATE_DIR=str(self.output),
                   DOCKER_WORKFLOW_SHA='f' * 40, GITHUB_RUN_ID='1', GITHUB_RUN_ATTEMPT='1')
        return subprocess.run([sys.executable, '-c', self.program], env=env, capture_output=True, text=True)

    def test_original_archive_metadata_and_checksum_match(self):
        archive = self.write_archive()
        result = self.execute()
        self.assertEqual(0, result.returncode, result.stderr)
        metadata = json.loads((self.output / 'candidate-metadata.json').read_bytes())
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), metadata['archive']['sha256'])
        self.assertEqual(LOCK['services'][0], metadata['source'])
        self.assertEqual('linux/amd64', metadata['platform'])
        self.assertEqual('unpublished-oci-candidate', metadata['kind'])
        self.assertNotIn('manifest_digest', metadata)
        self.assertNotIn('published_at', metadata)
        for line in (self.output / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ')
            self.assertEqual(digest, hashlib.sha256((self.output / name).read_bytes()).hexdigest())

    def test_wrong_architecture_rejected(self):
        self.write_archive(architecture='arm64')
        self.assertNotEqual(0, self.execute().returncode)
        self.assertFalse((self.output / 'candidate-metadata.json').exists())

    def test_wrong_source_rejected(self):
        self.write_archive(source_commit='e' * 40)
        self.assertNotEqual(0, self.execute().returncode)

    def test_missing_archive_rejected(self):
        self.assertNotEqual(0, self.execute().returncode)

    def test_corrupt_descriptor_rejected(self):
        self.write_archive(corrupt=True)
        self.assertNotEqual(0, self.execute().returncode)

    def test_missing_layer_rejected(self):
        self.write_archive(missing_layer=True)
        self.assertNotEqual(0, self.execute().returncode)


if __name__ == '__main__':
    unittest.main()
