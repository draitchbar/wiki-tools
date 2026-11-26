"""References to docs/adr.md resolve. Its decisions are numbered 1..N without
gaps, the index lists them in order, and every `docs/adr.md, N` (also
`docs/adr.md` N, `docs/adr.md`, N and M, ADR N, ADR N-M and K, a quoted
title) in a tracked file, and every cross-reference inside the ADR, names a
decision that exists (docs/development.md, "Recording a decision")."""

import re
import subprocess

import pytest

from conftest import TESTS

REPO = TESTS.parent
ADR = REPO / "docs" / "adr.md"
HEADING = re.compile(r"^## (\d+)\. (.+)$", re.M)
INDEX_ROW = re.compile(r"^\| (\d+) \| (.+?) \| .+ \|$", re.M)
# A list of numbers: "3", "3 and 11", "2, 5 and 9", "1-6 and 9".
NUMS = r"\d+(?:-\d+)?(?:(?:, | and )\d+(?:-\d+)?)*"
# docs/adr.md, N / `docs/adr.md`, N / docs/adr.md N / [ADR N](adr.md) / ADR N.
FILE_REF = re.compile(r"(?:adr\.md`?,? |\bADR )(" + NUMS + r")(?![\d-])")
TITLE_REF = re.compile(r"adr\.md`?, \"([^\"]+)\"")
# Inside the ADR: a number closing a parenthesis, "(11)", "(4, 15)",
# "(..., 3)", "(..., 13)".
INNER_REF = re.compile(r"(?:\(|, )(\d{1,2})\)")


def numbers(text):
    out = []
    for part in re.split(r", | and ", text):
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def decisions():
    return {int(n): title for n, title in HEADING.findall(ADR.read_text(encoding="utf-8"))}


def tracked_text_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
    for name in out.decode("utf-8").split("\0"):
        path = REPO / name
        if not name or name == "docs/adr.md" or not path.is_file():
            continue
        try:
            yield name, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


@pytest.mark.checks("adr/numbered-without-gaps")
def test_decisions_are_numbered_without_gaps():
    nums = [int(n) for n, _ in HEADING.findall(ADR.read_text(encoding="utf-8"))]
    assert nums == list(range(1, len(nums) + 1)), nums


@pytest.mark.checks("adr/index-matches-headings")
def test_index_lists_every_decision():
    rows = [(int(n), t) for n, t in INDEX_ROW.findall(ADR.read_text(encoding="utf-8"))]
    assert rows == sorted(decisions().items())


@pytest.mark.checks("adr/references-resolve")
def test_references_in_the_repo_resolve():
    known = decisions()
    titles = set(known.values())
    bad = []
    for name, text in tracked_text_files():
        for m in FILE_REF.finditer(text):
            bad.extend("%s: %s (no decision %d)" % (name, m.group(0), n)
                       for n in numbers(m.group(1)) if n not in known)
        bad.extend("%s: %s (no such title)" % (name, m.group(0))
                   for m in TITLE_REF.finditer(text) if m.group(1) not in titles)
    assert not bad, "\n".join(bad)


@pytest.mark.checks("adr/references-found")
def test_reference_scan_finds_references():
    # Guards the scan itself: a pattern that stopped matching would pass the
    # test above with nothing checked.
    found = sum(len(FILE_REF.findall(text)) for _, text in tracked_text_files())
    assert found > 50, found


@pytest.mark.checks("adr/cross-references-resolve")
def test_cross_references_inside_the_adr_resolve():
    known = decisions()
    text = ADR.read_text(encoding="utf-8")
    refs = [int(n) for n in INNER_REF.findall(text)]
    assert refs, "no cross-references found"
    assert [n for n in refs if n not in known] == []


@pytest.mark.parametrize("text, nums", [
    ("3", [3]), ("3 and 11", [3, 11]), ("2, 5 and 9", [2, 5, 9]), ("1-6 and 9", [1, 2, 3, 4, 5, 6, 9]),
], ids=["adr/numbers-one", "adr/numbers-and", "adr/numbers-list", "adr/numbers-range"])
def test_numbers(text, nums):
    assert numbers(text) == nums
