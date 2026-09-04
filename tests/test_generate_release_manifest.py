from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "generate_release_manifest", ROOT / "scripts" / "generate-release-manifest.py"
)
assert SPEC is not None and SPEC.loader is not None
manifest_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest_module)


class GenerateReleaseManifestTests(unittest.TestCase):
    release_id = "v1.3.0"
    published_at = "2026-07-18T07:08:09Z"

    def component(self, service: str, suffix: str) -> dict[str, object]:
        database_schema = (
            "backward_compatible"
            if service in {"control-panel", "observability"}
            else "none"
        )
        return {
            "service": service,
            "source_version": "v1.0.16",
            "commit": suffix * 40,
            "image": f"ghcr.io/kome-lab/autostream-docker/{service}:{self.release_id}",
            "manifest_digest": f"sha256:{suffix * 64}",
            "platform_digests": {
                "linux/amd64": f"sha256:{'a' * 64}",
                "linux/arm64": f"sha256:{'b' * 64}",
            },
            "rollback_compatible": True,
            "database_schema": database_schema,
        }

    def write_components(self, directory: Path) -> list[Path]:
        files: list[Path] = []
        for index, service in enumerate(manifest_module.EXPECTED_SERVICES):
            path = directory / f"{service}.json"
            path.write_text(
                json.dumps(self.component(service, str(index + 1))), encoding="utf-8"
            )
            files.append(path)
        updater = directory / "updater.json"
        updater.write_text(json.dumps({"service": "updater", "commit": "f" * 40, "protocol_major": 2}), encoding="utf-8")
        return files + [updater]

    def test_generates_stable_complete_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            files = self.write_components(Path(temp))
            manifest = manifest_module.generate_manifest(
                self.release_id, self.published_at, list(reversed(files))
            )

        self.assertEqual(2, manifest["schema_version"])
        self.assertEqual(self.release_id, manifest["release_id"])
        self.assertEqual("docker", manifest["channel"])
        self.assertEqual(self.published_at, manifest["published_at"])
        self.assertEqual(2, manifest["protocol_major"])
        self.assertEqual(
            {
                "schema_version",
                "release_id",
                "channel",
                "published_at",
                "protocol_major",
                "components",
            },
            set(manifest),
        )
        self.assertEqual(
            list(manifest_module.EXPECTED_COMPONENTS),
            [component["service"] for component in manifest["components"]],
        )
        self.assertEqual(
            ["linux/amd64", "linux/arm64"],
            list(manifest["components"][0]["platform_digests"]),
        )
        self.assertEqual({"service": "updater", "commit": "f" * 40, "protocol_major": 2}, manifest["components"][-1])
        for component in manifest["components"][:-1]:
            self.assertEqual(
                {
                    "service",
                    "source_version",
                    "commit",
                    "image",
                    "manifest_digest",
                    "platform_digests",
                    "rollback_compatible",
                    "database_schema",
                },
                set(component),
            )
            self.assertIs(component["rollback_compatible"], True)
            expected_schema = (
                "backward_compatible"
                if component["service"] in {"control-panel", "observability"}
                else "none"
            )
            self.assertEqual(expected_schema, component["database_schema"])

    def test_reproduces_canonical_contracts_v2_fixture(self) -> None:
        contracts_root = os.environ.get("AUTOSTREAM_CONTRACTS_ROOT")
        if not contracts_root:
            self.skipTest("AUTOSTREAM_CONTRACTS_ROOT not set")
        fixture_path = (
            Path(contracts_root) / "testdata" / "release-manifest.docker.generated.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            component_files = []
            for component in fixture["components"]:
                path = directory / f"{component['service']}.json"
                path.write_text(json.dumps(component), encoding="utf-8")
                component_files.append(path)
            generated = manifest_module.generate_manifest(
                fixture["release_id"], fixture["published_at"], component_files
            )
        self.assertEqual(fixture, generated)

    def test_rejects_missing_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            files = self.write_components(Path(temp))[:-1]
            with self.assertRaisesRegex(manifest_module.ManifestError, "missing.*updater"):
                manifest_module.generate_manifest(
                    self.release_id, self.published_at, files
                )

    def test_rejects_duplicate_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            files = self.write_components(directory)
            duplicate = directory / "duplicate.json"
            duplicate.write_text(files[0].read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(manifest_module.ManifestError, "duplicate"):
                manifest_module.generate_manifest(
                    self.release_id, self.published_at, files + [duplicate]
                )

    def test_rejects_wrong_bundle_tag(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            files = self.write_components(directory)
            component = json.loads(files[0].read_text(encoding="utf-8"))
            component["image"] = component["image"].replace("v1.3.0", "latest")
            files[0].write_text(json.dumps(component), encoding="utf-8")
            with self.assertRaisesRegex(manifest_module.ManifestError, "canonical"):
                manifest_module.generate_manifest(
                    self.release_id, self.published_at, files
                )

    def test_rejects_invalid_platform_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            files = self.write_components(directory)
            component = json.loads(files[0].read_text(encoding="utf-8"))
            component["platform_digests"]["linux/arm64"] = "sha256:not-a-digest"
            files[0].write_text(json.dumps(component), encoding="utf-8")
            with self.assertRaisesRegex(manifest_module.ManifestError, "linux/arm64"):
                manifest_module.generate_manifest(
                    self.release_id, self.published_at, files
                )

    def test_rejects_non_utc_generation_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            files = self.write_components(Path(temp))
            with self.assertRaisesRegex(manifest_module.ManifestError, "second precision"):
                manifest_module.generate_manifest(
                    self.release_id, "2026-07-18T16:08:09+09:00", files
                )

    def test_rejects_image_repository_that_does_not_match_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            files = self.write_components(directory)
            component = json.loads(files[0].read_text(encoding="utf-8"))
            component["image"] = component["image"].replace(
                "/control-panel:", "/worker:"
            )
            files[0].write_text(json.dumps(component), encoding="utf-8")
            with self.assertRaisesRegex(manifest_module.ManifestError, "canonical"):
                manifest_module.generate_manifest(
                    self.release_id, self.published_at, files
                )

    def test_rejects_noncanonical_ghcr_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            files = self.write_components(directory)
            component = json.loads(files[0].read_text(encoding="utf-8"))
            component["image"] = component["image"].replace(
                "ghcr.io/kome-lab/", "ghcr.io/example/"
            )
            files[0].write_text(json.dumps(component), encoding="utf-8")
            with self.assertRaisesRegex(manifest_module.ManifestError, "canonical"):
                manifest_module.generate_manifest(
                    self.release_id, self.published_at, files
                )

    def test_rejects_missing_or_unsafe_rollback_policy(self) -> None:
        cases = (
            (
                "missing rollback compatibility",
                lambda component: component.pop("rollback_compatible"),
                "rollback_compatible",
            ),
            (
                "rollback disabled",
                lambda component: component.__setitem__("rollback_compatible", False),
                "rollback_compatible",
            ),
            (
                "missing database schema",
                lambda component: component.pop("database_schema"),
                "database_schema",
            ),
            (
                "wrong database schema",
                lambda component: component.__setitem__("database_schema", "none"),
                "database_schema",
            ),
        )
        for name, mutate, expected_error in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                files = self.write_components(directory)
                component = json.loads(files[0].read_text(encoding="utf-8"))
                mutate(component)
                files[0].write_text(json.dumps(component), encoding="utf-8")
                with self.assertRaisesRegex(
                    manifest_module.ManifestError, expected_error
                ):
                    manifest_module.generate_manifest(
                        self.release_id, self.published_at, files
                    )

    def test_rejects_missing_or_invalid_exact_source_sha(self) -> None:
        for value in (None, "", "main", "a" * 39, "A" * 40):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp:
                files = self.write_components(Path(temp))
                component = json.loads(files[0].read_text(encoding="utf-8"))
                component["commit"] = value
                files[0].write_text(json.dumps(component), encoding="utf-8")
                with self.assertRaisesRegex(manifest_module.ManifestError, "commit"):
                    manifest_module.generate_manifest(self.release_id, self.published_at, files)

    def test_rejects_legacy_updater_metadata(self) -> None:
        for field, value in (("source_version", "v1.0.0"), ("image", "updater:latest"),
                             ("minimum_agent_version", "v1.7.0"), ("protocol_major", 1)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                files = self.write_components(Path(temp))
                component = json.loads(files[-1].read_text(encoding="utf-8"))
                component[field] = value
                files[-1].write_text(json.dumps(component), encoding="utf-8")
                with self.assertRaises(manifest_module.ManifestError):
                    manifest_module.generate_manifest(self.release_id, self.published_at, files)

    def test_writes_updater_compatible_sha256_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            manifest_path = directory / "release-manifest.json"
            checksum_path = directory / "release-manifest.json.sha256"
            manifest_path.write_bytes(b'{"schema_version":2}\n')

            digest = manifest_module.write_sha256_sidecar(
                manifest_path, checksum_path
            )

            expected = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            self.assertEqual(expected, digest)
            self.assertEqual(
                f"{expected}  release-manifest.json\n".encode("ascii"),
                checksum_path.read_bytes(),
            )

    def test_rejects_checksum_output_that_overwrites_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest_path = Path(temp) / "release-manifest.json"
            manifest_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(manifest_module.ManifestError, "differ"):
                manifest_module.write_sha256_sidecar(manifest_path, manifest_path)


if __name__ == "__main__":
    unittest.main()
