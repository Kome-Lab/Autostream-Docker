from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "publish-ghcr.yml").read_text(
    encoding="utf-8"
)
CI_WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
    encoding="utf-8"
)
SOURCE_VERSIONS = (ROOT / "source-versions.env").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
CONTRACTS_SHA = "e96ac056e73e00a04f0c22c73122b9f6e18e8b52"
CI_CONTRACTS_SHA = "612ceb539ee74180beae682c4290aba54c49c389"
CANDIDATE = (ROOT / ".github/workflows/release-candidate.yml").read_text(encoding="utf-8")


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

    def test_stable_latest_manifest_is_verified_against_version_digest(self) -> None:
        self.assertIn("- name: Verify latest manifest", WORKFLOW)
        verify_step = WORKFLOW.split("- name: Verify latest manifest", 1)[1].split(
            "- name:", 1
        )[0]
        self.assertIn(
            'if [[ ! "${VERSION}" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]]',
            verify_step,
        )
        self.assertIn("Skipping latest verification for non-stable version", verify_step)
        self.assertIn('"${image}:latest"', verify_step)
        self.assertIn("steps.manifest_meta.outputs.manifest_digest", verify_step)
        self.assertIn("for attempt in 1 2 3 4 5 6 7 8 9 10", verify_step)
        self.assertIn("timeout 15s docker buildx imagetools inspect", verify_step)
        self.assertIn(
            'if [[ "${latest_digest}" == "${expected_digest}" ]]', verify_step
        )
        self.assertIn("does not match the immutable version manifest", verify_step)
        self.assertTrue(verify_step.rstrip().endswith("exit 1"))

    def test_manual_registry_publish_is_not_documented_as_an_official_release(self) -> None:
        self.assertIn("Manual registry publish is diagnostic-only", README)
        self.assertIn("never use this path for the\nofficial release version", README)
        self.assertIn("a later tag workflow cannot reuse it", README)

    def test_manifest_sidecar_is_generated_verified_and_uploaded_together(self) -> None:
        self.assertIn("--checksum-output release-manifest.json.sha256", WORKFLOW)
        self.assertIn("sha256sum --check release-manifest.json.sha256", WORKFLOW)
        self.assertIn("(.schema_version == 2)", WORKFLOW)
        self.assertIn("(.protocol_major == 2)", WORKFLOW)
        self.assertIn("(.release_id == $version)", WORKFLOW)
        self.assertIn("(.published_at == $published_at)", WORKFLOW)
        self.assertIn('{service: "updater", commit: $commit, protocol_major: 2}', WORKFLOW)
        self.assertIn("UPDATER_SOURCE_COMMIT", WORKFLOW)
        self.assertNotIn("(.minimum_agent_version ==", WORKFLOW)
        self.assertNotIn("(.bundle_version ==", WORKFLOW)
        self.assertNotIn("(.generated_at ==", WORKFLOW)
        artifact_step = WORKFLOW.split(
            "- name: Upload release manifest workflow artifact", 1
        )[1].split("- name:", 1)[0]
        self.assertIn("release-manifest.json\n", artifact_step)
        self.assertIn("release-manifest.json.sha256", artifact_step)

    def test_release_manifest_uses_canonical_contracts_validator(self) -> None:
        self.assertIn("repository: Kome-Lab/Autostream-Contracts", WORKFLOW)
        self.assertIn(f"ref: {CONTRACTS_SHA}", WORKFLOW)
        self.assertIn(
            "cp release-manifest.json .contracts/testdata/release-manifest.docker.generated.json",
            WORKFLOW,
        )
        self.assertIn(
            "^TestDockerReleaseManifestGeneratorShapeValidatesAgainstSchema$",
            WORKFLOW,
        )

    def test_component_metadata_enforces_service_rollback_policy(self) -> None:
        self.assertIn("--arg commit '${{ steps.build_meta.outputs.source_commit }}'", WORKFLOW)
        self.assertIn("source commits differ between platforms", WORKFLOW)
        self.assertIn("rollback_compatible: true", WORKFLOW)
        self.assertIn(
            'database_schema: (if ($service == "control-panel" or $service == "observability") then "backward_compatible" else "none" end)',
            WORKFLOW,
        )
        self.assertIn(
            "if .service == \"updater\"", WORKFLOW
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


class DockerCIWorkflowContractTests(unittest.TestCase):
    def test_feature_ci_runs_every_python_test_and_rejects_zero_tests(self) -> None:
        self.assertIn("branches: [main, codex/bundle8b-physical-eol-001]", CI_WORKFLOW)
        self.assertIn(
            "python3 -m unittest discover -s tests -p 'test_*.py' -v",
            CI_WORKFLOW,
        )
        self.assertIn("^Ran [1-9][0-9]* tests? in ", CI_WORKFLOW)
        self.assertIn("zero Docker contract tests ran", CI_WORKFLOW)

    def test_feature_ci_pins_and_runs_canonical_contracts_validator(self) -> None:
        self.assertIn("repository: Kome-Lab/Autostream-Contracts", CI_WORKFLOW)
        self.assertIn(f"ref: {CI_CONTRACTS_SHA}", CI_WORKFLOW)
        self.assertIn("AUTOSTREAM_CONTRACTS_ROOT", CI_WORKFLOW)
        self.assertIn(
            "^TestDockerReleaseManifestGeneratorShapeValidatesAgainstSchema$",
            CI_WORKFLOW,
        )

    def test_updater_source_commit_is_exact_and_current(self) -> None:
        match = re.search(r"^UPDATER_SOURCE_COMMIT=([0-9a-f]+)$", SOURCE_VERSIONS, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual("794d0cd69dd1b3ca130101f7769aaf8ac1274ac8", match.group(1))


class V2DistributionContractTests(unittest.TestCase):
    def test_five_source_versions_and_preflight_map(self):
        versions = re.findall(r"^(\w+_SOURCE_VERSION)=(.+)$", SOURCE_VERSIONS, re.MULTILINE)
        self.assertEqual(5, len(versions))
        self.assertEqual({"v2.0.0"}, {value for _, value in versions})
        preflight, build = WORKFLOW.split("\n  publish:\n", 1)
        self.assertIn("source_map: ${{ steps.sources.outputs.source_map }}", preflight)
        self.assertIn("--mode publish", preflight)
        self.assertLess(preflight.index("--mode publish"), preflight.index("Login to GHCR"))
        self.assertIn("needs: release-preflight", build)
        self.assertIn("SOURCE_MAP: ${{ needs.release-preflight.outputs.source_map }}", build)
        self.assertIn("ref: ${{ steps.source_version.outputs.source_commit || steps.source_version.outputs.source_version }}", build)
        self.assertIn('--service "${SERVICE}" --checkout "${SOURCE_PATH}"', build)

    def test_v2_rechecks_after_build_and_pushes_same_loaded_image(self):
        build = WORKFLOW.split("- name: Build and optionally push", 1)[1].split("- name: Publish verified v2 image", 1)[0]
        self.assertIn("push: ${{ env.PUSH_IMAGES == 'true' && env.VERSION != 'v2.0.0' }}", build)
        self.assertIn("load: ${{ env.VERSION == 'v2.0.0' }}", build)
        publish = WORKFLOW.split("- name: Publish verified v2 image", 1)[1].split("- name: Record platform digest", 1)[0]
        self.assertLess(publish.index("--mode publish"), publish.index('docker push "${IMAGE_TAG}"'))
        self.assertNotIn("docker build", publish)
        self.assertIn("docker image inspect", publish)
        self.assertIn("steps.v2_push.outputs.digest || steps.build.outputs.digest", WORKFLOW)
        for name in ("Publish version manifest", "Publish latest manifest"):
            step = WORKFLOW.split("- name: " + name, 1)[1].split("- name:", 1)[0]
            self.assertLess(step.index("--mode publish"), step.index("docker buildx imagetools create"))

    def test_existing_platform_and_manifest_denominators_remain_strict(self):
        self.assertIn('"${#metadata_files[@]}" -ne 2', WORKFLOW)
        self.assertIn('source versions differ between platforms', WORKFLOW)
        self.assertIn('source commits differ between platforms', WORKFLOW)
        self.assertIn('missing or duplicate linux/amd64 metadata', WORKFLOW)
        self.assertIn('missing or duplicate linux/arm64 metadata', WORKFLOW)
        self.assertIn('(.components | length == 6)', WORKFLOW)
        self.assertIn('(.schema_version == 2)', WORKFLOW)

    def test_candidate_only_accepts_manual_branch_v2_and_read_permissions(self):
        trigger = CANDIDATE.split('\non:\n', 1)[1].split('\npermissions:', 1)[0]
        self.assertEqual(['workflow_dispatch'], re.findall(r'^  ([a-z_]+):$', trigger, re.MULTILINE))
        self.assertEqual(['version'], re.findall(r'^      ([a-z_]+):$', trigger, re.MULTILINE))
        self.assertIn('options: [v2.0.0]', trigger)
        preflight = CANDIDATE.split('\n  candidate:\n', 1)[0]
        self.assertIn('test "${GITHUB_REF_TYPE}" = branch', preflight)
        self.assertLess(preflight.index('test "${GITHUB_REF_TYPE}"'), preflight.index('--mode candidate'))
        self.assertIn('needs: candidate-preflight', CANDIDATE)
        self.assertNotRegex(CANDIDATE, re.compile(r'^\s+[a-z-]+: write$', re.MULTILINE), 'no write permission')
        self.assertEqual(['contents', 'contents', 'contents'], re.findall(r'^\s+([a-z-]+): read$', CANDIDATE, re.MULTILINE))
        self.assertNotIn('id-token:', CANDIDATE)
        self.assertNotIn('continue-on-error:', CANDIDATE)
        self.assertNotIn('login-action', CANDIDATE)
        self.assertNotRegex(CANDIDATE, r'gh (?:release|workflow|run)|docker push|:latest')
        self.assertEqual(['false'], re.findall(r'^\s+push: (.+)$', CANDIDATE, re.MULTILINE))

    def test_candidate_and_publish_use_the_same_ten_native_builds(self):
        def components(workflow):
            return re.findall(r'- service: (\S+)\n\s+repo: (\S+)\n\s+dockerfile: (\S+)', workflow)
        self.assertEqual(components(WORKFLOW), components(CANDIDATE))
        self.assertEqual(5, len(components(CANDIDATE)))
        targets = re.findall(r'- platform: (\S+)\n\s+arch: (\S+)\n\s+runner: (\S+)', CANDIDATE)
        self.assertEqual([('linux/amd64', 'amd64', 'ubuntu-24.04'), ('linux/arm64', 'arm64', 'ubuntu-24.04-arm')], targets)
        self.assertEqual(targets, re.findall(r'- platform: (\S+)\n\s+arch: (\S+)\n\s+runner: (\S+)', WORKFLOW))
        self.assertEqual(10, len(components(CANDIDATE)) * len(targets))
        self.assertIn('amd64/x86_64|arm64/aarch64)', CANDIDATE)
        self.assertIn('type=oci,dest=', CANDIDATE)
        for action in re.findall(r'uses: ([^\s]+)', CANDIDATE):
            self.assertRegex(action, r'@[0-9a-f]{40}$')
            self.assertIn(action, WORKFLOW)

    def test_pinned_recursive_submodules_and_checkout_sha(self):
        for workflow in (WORKFLOW, CANDIDATE):
            self.assertIn('submodules: recursive', workflow)
            self.assertNotIn('submodule update --remote', workflow)
            self.assertIn('--checkout "${SOURCE_PATH}"', workflow)
        self.assertIn('ref: ${{ steps.source.outputs.commit }}', CANDIDATE)
        self.assertIn('SOURCE_MAP: ${{ needs.candidate-preflight.outputs.source_map }}', CANDIDATE)

    def test_dave_recipe_keeps_native_cgo_and_build_identity(self):
        recipe = (ROOT / 'services/discord-bot/Dockerfile').read_text()
        self.assertNotIn('$BUILDPLATFORM', recipe)
        self.assertIn('test "${TARGETOS}/${TARGETARCH}" = "$(go env GOOS)/$(go env GOARCH)"', recipe)
        for required in ('cmake ninja-build g++ make pkg-config autoconf automake', 'libtool zip unzip tar',
                         'COPY third_party ./third_party', 'make -C third_party/discordgo/dave/libdave/cpp BUILD_TYPE=Release',
                         'vcpkg_commit=16c71a39e5a0fc0bdb3fad03beef8f38ee00ee3b',
                         'fetch --no-tags --no-write-fetch-head',
                         '-c core.bare=false diff --exit-code "$vcpkg_commit" -- .',
                         'CGO_ENABLED=1', 'CGO_CFLAGS=', 'CGO_LDFLAGS=', '-lstdc++ -lm -ldl -lpthread',
                         'FROM gcr.io/distroless/cc-debian13', 'USER nonroot:nonroot',
                         'ENV AUTOSTREAM_NODE_CONFIG=/etc/autostream-discord-bot/config.yml',
                         'ENTRYPOINT ["/usr/local/bin/autostream-discord-bot"]'):
            self.assertIn(required, recipe)
        self.assertNotIn('CGO_ENABLED=0', recipe)
        self.assertNotIn('fetch --all', recipe)
        self.assertNotIn('submodule update --remote', recipe)
        for field in ('Version=${VERSION}', 'Commit=${COMMIT}', 'BuildDate=${BUILD_DATE}'):
            self.assertIn(field, recipe)

    def test_worker_font_state_nonroot_and_build_identity(self):
        recipe = (ROOT / 'services/worker/Dockerfile').read_text()
        for required in ('FROM debian:trixie-slim', 'ca-certificates fontconfig fonts-noto-cjk',
                         'test -r /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                         'install -d -m 0750 -o 65532 -g 65532 /var/lib/autostream/worker',
                         'ENV AUTOSTREAM_SCENE_FONT_FILE=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                         'ENV AUTOSTREAM_NODE_CONFIG=/etc/autostream-worker/config.yml',
                         'USER 65532:65532', 'ENTRYPOINT ["/usr/local/bin/autostream-worker"]'):
            self.assertIn(required, recipe)
        for field in ('Version=${VERSION}', 'Commit=${COMMIT}', 'BuildDate=${BUILD_DATE}'):
            self.assertIn(field, recipe)


if __name__ == "__main__":
    unittest.main()
