#!/usr/bin/env python3
"""Build and validate the immutable AutoStream Docker release manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
PROTOCOL_MAJOR = 2
EXPECTED_SERVICES = (
    "control-panel",
    "discord-bot",
    "encoder-recorder",
    "observability",
    "worker",
)
EXPECTED_COMPONENTS = (*EXPECTED_SERVICES, "updater")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_PLATFORMS = ("linux/amd64", "linux/arm64")
VERSION_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:[.-][0-9A-Za-z.-]+)?$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PUBLISHED_AT_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class ManifestError(ValueError):
    """Raised when build metadata cannot form a trustworthy release manifest."""


def _required_string(component: dict[str, Any], key: str, source: Path) -> str:
    value = component.get(key)
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{source}: {key} must be a non-empty string")
    return value


def _validate_published_at(value: str) -> None:
    if not PUBLISHED_AT_RE.fullmatch(value):
        raise ManifestError("published_at must use RFC3339 UTC second precision")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ManifestError("published_at must be a valid RFC3339 timestamp") from exc


def _load_component(source: Path, release_id: str) -> dict[str, Any]:
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"{source}: cannot read component metadata: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{source}: component metadata must be a JSON object")

    service = _required_string(raw, "service", source)
    commit = _required_string(raw, "commit", source)
    if not COMMIT_RE.fullmatch(commit):
        raise ManifestError(f"{source}: commit must be an exact lowercase source SHA")
    if service == "updater":
        if set(raw) != {"service", "commit", "protocol_major"}:
            raise ManifestError(f"{source}: Updater metadata must contain only service, commit, protocol_major")
        if type(raw["protocol_major"]) is not int or raw["protocol_major"] != PROTOCOL_MAJOR:
            raise ManifestError(f"{source}: unsupported Updater protocol_major")
        return {"service": service, "commit": commit, "protocol_major": PROTOCOL_MAJOR}
    if service not in EXPECTED_SERVICES:
        raise ManifestError(f"{source}: unsupported service {service!r}")
    allowed = {"service", "source_version", "commit", "image", "manifest_digest",
               "platform_digests", "rollback_compatible", "database_schema"}
    if set(raw) - allowed:
        raise ManifestError(f"{source}: unsupported image component fields")

    source_version = _required_string(raw, "source_version", source)
    if not VERSION_RE.fullmatch(source_version):
        raise ManifestError(f"{source}: invalid source_version {source_version!r}")

    image = _required_string(raw, "image", source)
    expected_image = (
        f"ghcr.io/kome-lab/autostream-docker/{service}:{release_id}"
    )
    if image != expected_image:
        raise ManifestError(
            f"{source}: image must equal canonical ref {expected_image}"
        )

    manifest_digest = _required_string(raw, "manifest_digest", source)
    if not DIGEST_RE.fullmatch(manifest_digest):
        raise ManifestError(f"{source}: invalid manifest_digest {manifest_digest!r}")

    platform_digests = raw.get("platform_digests")
    if not isinstance(platform_digests, dict):
        raise ManifestError(f"{source}: platform_digests must be a JSON object")
    if set(platform_digests) != set(EXPECTED_PLATFORMS):
        raise ManifestError(
            f"{source}: platform_digests must contain exactly "
            + ", ".join(EXPECTED_PLATFORMS)
        )
    for platform in EXPECTED_PLATFORMS:
        digest = platform_digests[platform]
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
            raise ManifestError(f"{source}: invalid digest for {platform}: {digest!r}")

    if raw.get("rollback_compatible") is not True:
        raise ManifestError(f"{source}: rollback_compatible must be true")
    expected_database_schema = (
        "backward_compatible"
        if service in {"control-panel", "observability"}
        else "none"
    )
    database_schema = raw.get("database_schema")
    if database_schema != expected_database_schema:
        raise ManifestError(
            f"{source}: database_schema for {service} must be "
            f"{expected_database_schema!r}"
        )

    return {
        "service": service,
        "source_version": source_version,
        "commit": commit,
        "image": image,
        "manifest_digest": manifest_digest,
        "platform_digests": {
            platform: platform_digests[platform] for platform in EXPECTED_PLATFORMS
        },
        "rollback_compatible": True,
        "database_schema": database_schema,
    }


def generate_manifest(
    release_id: str, published_at: str, component_files: list[Path]
) -> dict[str, Any]:
    if not VERSION_RE.fullmatch(release_id):
        raise ManifestError(f"invalid release_id {release_id!r}")
    _validate_published_at(published_at)

    components_by_service: dict[str, dict[str, Any]] = {}
    for source in component_files:
        component = _load_component(source, release_id)
        service = component["service"]
        if service in components_by_service:
            raise ManifestError(f"duplicate component metadata for {service}")
        components_by_service[service] = component

    missing = [service for service in EXPECTED_COMPONENTS if service not in components_by_service]
    if missing:
        raise ManifestError("missing component metadata for: " + ", ".join(missing))

    return {
        "schema_version": SCHEMA_VERSION,
        "release_id": release_id,
        "channel": "docker",
        "published_at": published_at,
        "protocol_major": PROTOCOL_MAJOR,
        "components": [components_by_service[service] for service in EXPECTED_COMPONENTS],
    }


def write_sha256_sidecar(manifest_path: Path, checksum_path: Path) -> str:
    """Write the checksum format consumed by autostream-updater."""
    if manifest_path.resolve() == checksum_path.resolve():
        raise ManifestError("checksum output must differ from the manifest output")
    try:
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ManifestError(f"cannot read generated manifest: {exc}") from exc

    try:
        checksum_path.parent.mkdir(parents=True, exist_ok=True)
        checksum_path.write_bytes(
            f"{digest}  {manifest_path.name}\n".encode("ascii")
        )
    except OSError as exc:
        raise ManifestError(f"cannot write manifest checksum: {exc}") from exc
    return digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--checksum-output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = generate_manifest(
            release_id=args.release_id,
            published_at=args.published_at,
            component_files=sorted(args.input_dir.glob("*.json")),
        )
    except ManifestError as exc:
        raise SystemExit(f"release manifest validation failed: {exc}") from exc

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        write_sha256_sidecar(args.output, args.checksum_output)
    except (OSError, ManifestError) as exc:
        raise SystemExit(f"release manifest output failed: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
