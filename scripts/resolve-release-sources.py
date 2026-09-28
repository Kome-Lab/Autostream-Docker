#!/usr/bin/env python3
"""Resolve the reviewed v2 source set. This tool has no publication operations."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


RELEASE = "v2.0.0"
OWNER = "Kome-Lab"
REPOSITORIES = {
    "control-panel": "Autostream-ControlPanel",
    "discord-bot": "Autostream-DiscordBot",
    "encoder-recorder": "Autostream-Encoder-Recorder",
    "observability": "Autostream-Observability",
    "worker": "Autostream-Worker",
}
API = "https://api.github.com"
SHA = re.compile(r"[0-9a-f]{40}\Z")


class SourceError(ValueError):
    pass


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise SourceError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json(text):
    return json.loads(text, object_pairs_hook=unique_object)


def exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise SourceError(f"{label}: unexpected or missing keys")


def valid_sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def validate_lock(lock):
    exact_keys(lock, ("schema_version", "release_id", "services"), "lock")
    if type(lock["schema_version"]) is not int or lock["schema_version"] != 1:
        raise SourceError("unsupported source-lock schema_version")
    if lock["release_id"] != RELEASE:
        raise SourceError("source-lock release_id must be v2.0.0")
    if not isinstance(lock["services"], list) or len(lock["services"]) != 5:
        raise SourceError("source-lock requires exactly five services")
    sources = {}
    for row in lock["services"]:
        exact_keys(row, ("service", "repository", "source_version", "commit", "dockerfile"), "service")
        name = row["service"]
        if not isinstance(name, str) or name not in REPOSITORIES or name in sources:
            raise SourceError("unknown or duplicate service")
        if row["repository"] != f"{OWNER}/{REPOSITORIES[name]}":
            raise SourceError(f"{name}: repository does not match reviewed owner/repository")
        if row["dockerfile"] != f"services/{name}/Dockerfile":
            raise SourceError(f"{name}: Dockerfile does not match service")
        if row["source_version"] != RELEASE or not valid_sha(row["commit"]):
            raise SourceError(f"{name}: expected v2.0.0 and lowercase full commit SHA")
        sources[name] = dict(row)
    if set(sources) != set(REPOSITORIES):
        raise SourceError("missing service")
    return {name: sources[name] for name in REPOSITORIES}


def read_github(path):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(API + path, headers=headers), timeout=30) as response:
            # A repository redirect is not an owner/repository equivalence proof.
            if response.url != API + path:
                raise SourceError("source API redirected to a different identity")
            return load_json(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SourceError(f"source lookup failed: HTTP {exc.code}") from None
    except URLError:
        raise SourceError("source lookup unavailable") from None


def resolve_tag(repository, version, read_json=None):
    read_json = read_github if read_json is None else read_json
    base = f"/repos/{repository}/git"
    ref = read_json(f"{base}/ref/tags/{version}")
    if (not isinstance(ref, dict) or ref.get("ref") != f"refs/tags/{version}"
            or ref.get("url") != f"{API}{base}/refs/tags/{version}"):
        raise SourceError("missing, ambiguous or wrong-repository tag ref")
    obj = ref.get("object")
    visited = set()
    for _ in range(16):
        if not isinstance(obj, dict) or not valid_sha(obj.get("sha")):
            raise SourceError("malformed tag object")
        kind, sha = obj.get("type"), obj["sha"]
        if kind not in ("tag", "commit") or sha in visited:
            raise SourceError("tag does not resolve unambiguously to a commit")
        visited.add(sha)
        path = f"{base}/{'tags' if kind == 'tag' else 'commits'}/{sha}"
        if obj.get("url") != API + path:
            raise SourceError("tag object belongs to a different repository")
        value = read_json(path)
        if not isinstance(value, dict) or value.get("sha") != sha or value.get("url") != API + path:
            raise SourceError("tag/commit object identity mismatch")
        if kind == "commit":
            return sha
        obj = value.get("object")
    raise SourceError("annotated tag nesting exceeds limit")


def resolve_sources(lock, mode, version=RELEASE, owner=OWNER, inputs=None, read_json=None):
    sources = validate_lock(lock)
    if mode not in ("candidate", "publish") or version != RELEASE or owner != OWNER:
        raise SourceError("v2 requires candidate/publish, v2.0.0 and Kome-Lab")
    inputs = {} if inputs is None else inputs
    if set(inputs) - set(REPOSITORIES) or any(value not in ("", RELEASE) for value in inputs.values()):
        raise SourceError("v2 service inputs must be empty or v2.0.0")
    if mode == "publish":
        # Return no map until every provider has passed. Never return a partial set.
        for source in sources.values():
            if resolve_tag(source["repository"], RELEASE, read_json) != source["commit"]:
                raise SourceError(f"{source['service']}: source tag differs from locked commit")
    return sources


def verify_checkout(source, checkout):
    def git(*args):
        result = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True, check=False)
        if result.returncode:
            raise SourceError("cannot read checked-out source identity")
        return result.stdout

    if git("rev-parse", "HEAD").strip() != source["commit"]:
        raise SourceError("checkout HEAD differs from locked commit")
    if source["service"] == "discord-bot":
        states = git("submodule", "status", "--recursive").splitlines()
        if not states or any(not line.startswith(" ") for line in states):
            raise SourceError("DAVE submodules must be initialized at every recorded gitlink")
        if not any(" third_party/discordgo/dave/libdave " in line + " " for line in states):
            raise SourceError("pinned libdave submodule is missing")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path(__file__).resolve().parents[1] / "release/v2.0.0-source-lock.json")
    parser.add_argument("--mode", choices=("candidate", "publish"), required=True)
    parser.add_argument("--version", default=RELEASE)
    parser.add_argument("--source-owner", default=OWNER)
    parser.add_argument("--service", choices=tuple(REPOSITORIES))
    parser.add_argument("--checkout", type=Path)
    args = parser.parse_args()
    try:
        sources = resolve_sources(load_json(args.lock.read_text(encoding="utf-8")), args.mode,
                                  args.version, args.source_owner,
                                  {name: os.environ.get(name.upper().replace("-", "_") + "_INPUT", "")
                                   for name in REPOSITORIES})
        if args.checkout:
            if not args.service:
                raise SourceError("checkout verification requires --service")
            verify_checkout(sources[args.service], args.checkout)
        print(json.dumps(sources, separators=(",", ":")))
    except (SourceError, OSError, ValueError) as exc:
        print(f"release source verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
