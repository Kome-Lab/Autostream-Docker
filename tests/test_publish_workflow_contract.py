from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "publish-ghcr.yml").read_text(
    encoding="utf-8"
)


class PublishWorkflowContractTests(unittest.TestCase):
    def test_workflow_uses_only_standard_docker_build_infrastructure(self) -> None:
        runner_labels = set(
            re.findall(r"^\s+(?:runs-on|runner): (.+)$", WORKFLOW, re.MULTILINE)
        )
        self.assertEqual(
            {"ubuntu-24.04", "ubuntu-24.04-arm", "${{ matrix.target.runner }}"},
            runner_labels,
        )
        docker_build_actions = re.findall(
            r"uses: (docker/(?:setup-buildx|build-push)-action)@([^\s]+)",
            WORKFLOW,
        )
        self.assertGreaterEqual(len(docker_build_actions), 3)
        self.assertEqual(
            {"docker/setup-buildx-action", "docker/build-push-action"},
            {action for action, _ in docker_build_actions},
        )
        for action, ref in docker_build_actions:
            self.assertRegex(ref, r"^[0-9a-f]{40}$", action)
        self.assertNotRegex(
            WORKFLOW,
            r"uses: (?!docker/)[^\s]*/(?:setup-docker-builder|build-push-action)@",
        )

    def test_official_artifact_actions_are_pinned_to_full_shas(self) -> None:
        official_uses = re.findall(
            r"uses: (actions/(?:upload-artifact|download-artifact|attest-build-provenance))@([^\s]+)",
            WORKFLOW,
        )
        self.assertGreaterEqual(len(official_uses), 7)
        for action, ref in official_uses:
            self.assertRegex(ref, r"^[0-9a-f]{40}$", action)

    def test_matrix_fans_in_via_uniquely_named_artifacts(self) -> None:
        self.assertIn(
            "name: image-metadata-${{ matrix.component.service }}-${{ matrix.target.arch }}",
            WORKFLOW,
        )
        self.assertIn("pattern: image-metadata-${{ matrix.component.service }}-*", WORKFLOW)
        self.assertIn("name: release-component-${{ matrix.component.service }}", WORKFLOW)
        self.assertIn("pattern: release-component-*", WORKFLOW)

    def test_dispatch_versions_are_not_interpolated_into_shell_source(self) -> None:
        for name in (
            "control_panel_version",
            "discord_bot_version",
            "encoder_recorder_version",
            "observability_version",
            "worker_version",
        ):
            self.assertEqual(WORKFLOW.count("${{ inputs." + name + " }}"), 1, name)
        self.assertIn('source_version="${CONTROL_PANEL_INPUT}"', WORKFLOW)

    def test_tag_release_attaches_but_never_overwrites_manifest(self) -> None:
        self.assertIn("if: github.ref_type == 'tag'", WORKFLOW)
        self.assertIn("release-preflight:", WORKFLOW)
        self.assertIn("needs: release-preflight", WORKFLOW)
        self.assertIn("GitHub Release ${VERSION} already exists", WORKFLOW)
        self.assertIn("GHCR tag ${ref} already exists", WORKFLOW)
        self.assertIn('gh release create "${VERSION}"', WORKFLOW)
        self.assertGreaterEqual(WORKFLOW.count("release-manifest.json.sha256"), 4)
        self.assertNotIn('gh release upload "${VERSION}"', WORKFLOW)
        self.assertNotIn("gh release upload --clobber", WORKFLOW)

    def test_manifest_sidecar_is_generated_verified_and_uploaded_together(self) -> None:
        self.assertIn("--checksum-output release-manifest.json.sha256", WORKFLOW)
        self.assertIn("sha256sum --check release-manifest.json.sha256", WORKFLOW)
        self.assertIn('(.minimum_agent_version == "v1.7.0")', WORKFLOW)
        self.assertIn("(.release_id == $version)", WORKFLOW)
        self.assertIn("(.bundle_version == $version)", WORKFLOW)
        self.assertIn("(.published_at == $generated_at)", WORKFLOW)
        self.assertIn("(.generated_at == $generated_at)", WORKFLOW)
        artifact_step = WORKFLOW.split(
            "- name: Upload release manifest workflow artifact", 1
        )[1].split("- name:", 1)[0]
        self.assertIn("release-manifest.json\n", artifact_step)
        self.assertIn("release-manifest.json.sha256", artifact_step)

    def test_component_metadata_enforces_service_rollback_policy(self) -> None:
        self.assertIn("rollback_compatible: true", WORKFLOW)
        self.assertIn(
            'database_schema: (if ($service == "control-panel" or $service == "observability") then "backward_compatible" else "none" end)',
            WORKFLOW,
        )
        self.assertIn(
            "all(.components[]; .rollback_compatible == true)", WORKFLOW
        )
        self.assertIn(
            'then .database_schema == "backward_compatible"', WORKFLOW
        )
        self.assertIn('else .database_schema == "none"', WORKFLOW)

    def test_release_job_has_attestation_and_release_permissions(self) -> None:
        release_job = WORKFLOW.split("\n  release-manifest:\n", 1)[1]
        self.assertIn("attestations: write", release_job)
        self.assertIn("contents: write", release_job)
        self.assertIn("id-token: write", release_job)


if __name__ == "__main__":
    unittest.main()
