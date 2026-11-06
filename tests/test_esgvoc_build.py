"""
Full esgvoc build of this repo against the latest WCRP-universe, reported as WARNINGS only.

`esgvoc admin validate --schema-only` (what CI runs) never links terms to the universe, so
it misses things only a real build finds (skipped term files, missing universe terms, ...).
This test runs the real build but never fails: differences from the universe are expected
while this repo's terms are not merged there yet. Read them in pytest's "warnings summary".

Environment variables:
  OBS4MIPS_SKIP_ESGVOC_BUILD=1     skip this test (it clones the universe and takes ~1 min)
  OBS4MIPS_UNIVERSE_REF=<ref>      universe branch/tag to build against (default: its default
                                   branch, currently "main"); e.g. a branch carrying the
                                   obs4MIPs terms
  OBS4MIPS_UNIVERSE_REPO=<url>     universe repository (default: WCRP-CMIP/WCRP-universe)
"""

import collections
import os
import re
import subprocess
import sys
import warnings

import pytest

UNIVERSE_REPO = os.environ.get(
    "OBS4MIPS_UNIVERSE_REPO", "https://github.com/WCRP-CMIP/WCRP-universe"
)
UNIVERSE_REF = os.environ.get("OBS4MIPS_UNIVERSE_REF")  # None = default branch
ESGVOC = [sys.executable, "-c", "from esgvoc.cli.main import app; app()"]


class EsgvocBuildWarning(UserWarning):
    """A difference between this repo and the universe found by a full esgvoc build."""


def _run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def parse_ingestion_failures(log):
    """Return [(collection, file name, error message)] from an esgvoc build log."""
    failures = []
    for chunk in log.split("INGESTION FAILURE")[1:]:
        file = re.search(r"File: (.+)", chunk)
        coll = re.search(r"Collection: (.+)", chunk)
        msg = re.search(r"Error Message: (.+)", chunk)
        if file and coll and msg:
            failures.append(
                (
                    coll.group(1).strip(),
                    os.path.basename(file.group(1).strip()),
                    msg.group(1).strip(),
                )
            )
    return failures


def summarize(failures, universe_label):
    """One warning text per (collection, reason)."""
    groups = collections.defaultdict(list)
    for coll, file, msg in failures:
        missing = re.search(r"No such file or directory: '.*?/([^/']+/[^/']+)'", msg)
        reason = (
            "links to a universe term that does not exist"
            if missing
            else msg
        )
        groups[(coll, reason)].append(file)
    return [
        f"[{coll}] {len(files)} term(s) not built against {universe_label}: {reason}; "
        f"e.g. {', '.join(sorted(set(files))[:3])}"
        for (coll, reason), files in sorted(groups.items())
    ]


@pytest.mark.esgvoc_build
def test_esgvoc_build_against_latest_universe(repo_root, tmp_path):
    if os.environ.get("OBS4MIPS_SKIP_ESGVOC_BUILD"):
        pytest.skip("OBS4MIPS_SKIP_ESGVOC_BUILD is set")

    def announce(text):
        warnings.warn(EsgvocBuildWarning(text), stacklevel=1)

    universe = tmp_path / "universe"
    clone = ["git", "clone", "-q", "--depth", "1"]
    if UNIVERSE_REF:
        clone += ["--branch", UNIVERSE_REF]
    try:
        cloned = _run(clone + [UNIVERSE_REPO, str(universe)], timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        announce(f"esgvoc build NOT RUN: could not clone the universe ({e})")
        return
    if cloned.returncode != 0:
        announce(f"esgvoc build NOT RUN: git clone failed: {cloned.stderr.strip()[:200]}")
        return
    label = f"universe {UNIVERSE_REF or 'default branch'}"

    db = tmp_path / "obs4mips.db"
    args = [
        "admin", "build",
        "-p", str(repo_root),
        "-u", str(universe),
        "--project-id", "obs4mips",
        "--cv-version", "dev",
        "--universe-version", "dev",
        "-o", str(db),
    ]
    try:
        build = _run(ESGVOC + args, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as e:
        announce(f"esgvoc build NOT RUN ({e})")
        return

    log = build.stdout + build.stderr
    failures = parse_ingestion_failures(log)
    for text in summarize(failures, label):
        announce(text)
    if build.returncode != 0 and not failures:
        announce(f"esgvoc build failed against {label} without term errors: {log.strip()[-300:]}")
    # Deliberately no assertion: this test only announces.
