# AutoStream Dockerfiles

This repository stores Dockerfiles for AutoStream runtime services.

Runtime environment values are supplied by the deployment compose file, not by
these images. Only Control Panel and Observability require `DATABASE_URL`.
Encoder/Recorder, Worker, and Discord Bot do not have their own MariaDB
database; they receive runtime configuration from Control Panel.

Node services expect a Panel-generated Node Agent config mounted at
`/etc/autostream-<service>/config.yml` by default. Compose files may point
`AUTOSTREAM_NODE_CONFIG` at a service-specific read-only mount when multiple
nodes run on the same host. Service images run as nonroot, so bind-mounted
config files should be readable by container group `65532` and kept non-world
readable, for example `root:65532` with mode `0640`.

## Services

- `services/control-panel/Dockerfile`
- `services/discord-bot/Dockerfile`
- `services/encoder-recorder/Dockerfile`
- `services/observability/Dockerfile`
- `services/worker/Dockerfile`

## Publish Images

The GitHub Actions workflow in `.github/workflows/publish-ghcr.yml` builds all service images and publishes them to GHCR when publication is enabled.
For releases other than `v2.0.0`, services can have different source repository versions. The workflow resolves each service source tag in this order:

1. Matching workflow dispatch input such as `control_panel_version` or `worker_version`.
2. `source-versions.env` in this repository.
3. The Docker image `version` input or pushed tag.

Image names:

- `ghcr.io/<owner>/autostream-docker/control-panel:<version>`
- `ghcr.io/<owner>/autostream-docker/discord-bot:<version>`
- `ghcr.io/<owner>/autostream-docker/encoder-recorder:<version>`
- `ghcr.io/<owner>/autostream-docker/observability:<version>`
- `ghcr.io/<owner>/autostream-docker/worker:<version>`

Current default source tags are pinned in `source-versions.env`.

### v2.0.0 source identity

`release/v2.0.0-source-lock.json` records the five reviewed provider commits,
repository identities, source versions and Dockerfile paths. The source lock is
an input to a candidate build, not a published release manifest. All five source
versions are `v2.0.0`; the owner must be `Kome-Lab`, and manual service-version
inputs must be empty or `v2.0.0`.

Before any v2 image is published, `release-preflight` resolves every provider's
`v2.0.0` tag, including annotated tags, to a commit and compares it with the
source lock. A missing or different tag fails the entire preflight. The matrix
consumes that one verified source map and checks out full SHAs, including fixed
recursive submodules, then verifies the actual HEAD. It never follows a changed
tag to a different build source.

Each v2 image is first built and loaded on its native runner. Immediately before
pushing the same image, the workflow checks its source label and architecture,
rechecks all five tags and verifies checkout identity. It also rechecks tags
before version/latest manifest and release publication. These checks detect
observed drift; they cannot atomically freeze refs across five repositories.
Publication still requires the separate release gates and immutable target checks.

### Private candidates before source tags exist

`.github/workflows/release-candidate.yml` is a separate `workflow_dispatch`-only
build path for a branch ref and version `v2.0.0`. It resolves the lock without
requiring source tags, checks out those commits and builds the same five services
on native `linux/amd64` and `linux/arm64` runners. A tag ref is rejected before
building. The workflow has read-only repository permissions, no registry login
and fixed `push: false`; there is no publication toggle.

Each of the ten matrix entries uploads an OCI archive, `candidate-metadata.json`
and `SHA256SUMS` as a candidate workflow artifact. Metadata records provider
commit/version, the actual Docker workflow source SHA, Dockerfile/lock hashes,
the architecture read from the OCI config, run ID/attempt and measured archive
hash. The archive's descriptors, layers and source labels are checked before
upload. Missing output or a mismatched identity fails the job. This format is
separate from canonical `release-manifest.json` and contains no claim of a
published registry digest or publication time.

For a local unsigned rehearsal, record the Docker base SHA and the exact patch
and untracked-file hashes; do not assign an invented Docker commit. A local test
or candidate artifact does not establish independent CI acceptance, two-platform
runtime acceptance, release publication or production rollout.

### Runtime packaging

Discord Bot uses the accepted pinned libdave/DiscordGo sources and native CGO
build recipe on each architecture, with the trixie C++ runtime libraries. Source
checkouts must include recursive submodules at their recorded gitlinks; do not
use `submodule update --remote` or disable DAVE to make a build pass.
Because Docker contexts do not retain usable parent Git metadata, the Bot build
stage restores the vcpkg history reachable from its accepted full gitlink SHA
and verifies that the copied vcpkg sources match that commit. This supplies the
existing versioned-port baseline lookup without changing dependency pins. That
Git history stays in the build stage and is not copied into the runtime image.

Worker includes `fontconfig` and `fonts-noto-cjk` on `debian:trixie-slim`.
`AUTOSTREAM_SCENE_FONT_FILE` defaults to
`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`, and
`/var/lib/autostream/worker` is created with mode `0750`, owned by `65532:65532`.
A bind mount replacing that directory must preserve usable ownership and mode.

`UPDATER_SOURCE_COMMIT` remains
`794d0cd69dd1b3ca130101f7769aaf8ac1274ac8`. Its correspondence with the final
Updater application artifact remains a separate release gate; changing the five
provider versions does not resolve that identity or update aggregate source pins.

Build runners:

- `linux/amd64` builds run on the GitHub-hosted `ubuntu-24.04` runner.
- `linux/arm64` builds run on the GitHub-hosted `ubuntu-24.04-arm` runner.

Each architecture build pushes an architecture-specific tag such as
`<version>-amd64` or `<version>-arm64`. When publishing is enabled, the
workflow then creates the multi-architecture `<version>` manifest and, for
stable release tags, the `latest` manifest.

The multi-architecture manifest is assembled from the immutable digest returned
by each architecture build, not by resolving the architecture tags again. The
workflow inspects the published manifest and fails if its `linux/amd64` or
`linux/arm64` child digest differs from the corresponding build result. For a
stable release it also waits for `latest` to resolve and fails unless its digest
matches the immutable `<version>` manifest digest.

## Release Manifest Contract

A successful pushed tag publish creates a GitHub Release for that new tag and
attaches `release-manifest.json` plus the updater-required
`release-manifest.json.sha256` sidecar. The sidecar uses the standard
`<64 lowercase hex>  release-manifest.json` format. Stable releases become the repository's
`releases/latest`; prerelease versions such as `v1.3.0-rc.1` are created as
GitHub prereleases. An existing manifest or checksum asset is never
overwritten. This makes the release assets suitable for Control Panel update
discovery: a Docker bundle is updateable only when the latest release contains
this asset and all six required components validate.

The release manifest has this versioned JSON contract:

```json
{
  "schema_version": 2,
  "release_id": "v1.3.0",
  "channel": "docker",
  "published_at": "2026-07-18T07:08:09Z",
  "protocol_major": 2,
  "components": [
    {
      "service": "control-panel",
      "source_version": "v1.6.8",
      "commit": "<40 lowercase hex characters>",
      "image": "ghcr.io/kome-lab/autostream-docker/control-panel:v1.3.0",
      "manifest_digest": "sha256:<64 lowercase hex characters>",
      "platform_digests": {
        "linux/amd64": "sha256:<64 lowercase hex characters>",
        "linux/arm64": "sha256:<64 lowercase hex characters>"
      },
      "rollback_compatible": true,
      "database_schema": "backward_compatible"
    }
  ]
}
```

`release_id`, `channel`, and `published_at` are the shared AutoStream release
envelope. For this repository, `channel` is always `docker`.
The abbreviated example shows one image component; a complete manifest also
contains the other four image components and the independent Updater component.
The canonical schema is version 2 with `protocol_major: 2`. Legacy envelope
fields `bundle_version`, `generated_at` and `minimum_agent_version` are rejected.

`components` always contains exactly `control-panel`, `discord-bot`,
`encoder-recorder`, `observability`, `worker`, and `updater`, in that order.
The Updater component contains exactly `service`, its full `commit` and
`protocol_major: 2`; it has no service-image fields. Each of the five image
components records its full provider `commit`. `image` is the
canonical `ghcr.io/kome-lab/autostream-docker/<service>:<release_id>` ref,
while `manifest_digest` and `platform_digests` are immutable
registry identities. Consumers must verify `release-manifest.json.sha256`
before parsing the JSON and should deploy by
`<image repository>@<manifest_digest>` and treat the tag as display metadata.
They must reject unknown schema versions, missing or duplicate services,
malformed digests, image tags that do not match `release_id`, and missing or
unsafe rollback policy fields. Every image component declares
`rollback_compatible: true`. `control-panel` and `observability` declare
`database_schema: backward_compatible`; `discord-bot`, `encoder-recorder`, and
`worker` declare `database_schema: none`. This contract must be validated before
an updater pulls an image or runs `docker compose up`, because a failed update
may automatically restore the prior image after a database migration.

The build matrix cannot expose a reliable combined output directly. Each build
therefore uploads one uniquely named digest metadata artifact. Per-service jobs
download and validate the two platform artifacts, publish one multi-arch image,
and upload one component artifact. The final job downloads all five component
artifacts, adds the independently pinned Updater component and runs
`scripts/generate-release-manifest.py`, which enforces the
contract before creating the GitHub Release.

When GitHub artifact attestations are available for the repository plan, the
workflow publishes provenance for each multi-arch image and for
`release-manifest.json`. Attestation failure is reported as a workflow warning
because private-repository availability depends on the GitHub plan; digest and
release publication still complete. All official GitHub Actions used for
artifact transfer and attestation are pinned to full commit SHAs.

Operators can download and inspect a release manifest with:

```bash
gh release download v1.3.0 --pattern 'release-manifest.json*'
sha256sum --check release-manifest.json.sha256
jq . release-manifest.json
```

Where attestations are available, verify the downloaded asset with:

```bash
gh attestation verify release-manifest.json --repo <owner>/Autostream-Docker
```

GitHub-hosted runners are ephemeral. The publish workflow does not configure a
provider-specific persistent Docker layer cache, so cache state is not retained
between jobs.

Manual dry-run:

```bash
gh workflow run publish-ghcr.yml -f version=v1.3.0 -f source_owner=<owner> -f push_images=false
```

Manual dry-run with mixed service source versions:

```bash
gh workflow run publish-ghcr.yml \
  -f version=v1.3.0 \
  -f source_owner=<owner> \
  -f control_panel_version=v1.3.0 \
  -f discord_bot_version=v1.0.8 \
  -f encoder_recorder_version=v1.0.8 \
  -f observability_version=v1.0.10 \
  -f worker_version=v1.0.8 \
  -f push_images=false
```

Manual registry publish is diagnostic-only. It does not create a GitHub Release,
so use a pushed tag for a Control Panel-discoverable bundle. Because GHCR tags
are immutable in this workflow, a successful manual publish consumes that
version and a later tag workflow cannot reuse it; never use this path for the
official release version:

```bash
gh workflow run publish-ghcr.yml -f version=v1.3.0 -f source_owner=<owner> -f push_images=true
```

If the source repositories are private, set one of these repository secrets in `Autostream-Docker`:

- `AUTOSTREAM_SOURCE_TOKEN` with read access to the private source repositories.
- `GITHUBTOKEN` with read access to the private source repositories. This name is also used for GHCR login when present.

The built-in `GITHUB_TOKEN` is only enough when the source repositories are public or otherwise readable by the workflow. Do not put provider secrets or runtime `.env` values in this repository.
