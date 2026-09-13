"""Repository-wide consistency checks on every assessment_rules block.

These walk the shipped YAML rather than a fixture, so a new module - or a future
per-beamline override - is covered the moment it is added. They are the tests
that catch configuration mistakes which the arithmetic cannot: a check type no
dispatcher implements, a limits list of the wrong length or in the wrong order,
and duplicate keys that PyYAML silently discards.
"""

import os

import pytest
import yaml

from conftest import MODULES_DIR, all_rule_blocks


RULE_BLOCKS = all_rule_blocks()


def test_some_rule_blocks_were_found():
    """Guard against the walker silently finding nothing and passing."""
    assert RULE_BLOCKS, "no assessment_rules blocks found - has the layout changed?"


@pytest.mark.parametrize(
    "label,path,rules", RULE_BLOCKS, ids=[b[0] for b in RULE_BLOCKS]
)
def test_every_rule_is_well_formed(assessor, label, path, rules):
    """Every rule must name a known check type and carry usable limits.

    A failure here means the report would show that parameter as unassessed.
    Before the shared engine it meant the parameter silently showed "danger",
    or silently showed nothing at all, depending which module it was in.
    """
    problems = []
    for name, rule in rules.items():
        problems.extend(assessor.validate_assessment_rule(name, rule or {}))
    assert not problems, f"{label}:\n  " + "\n  ".join(problems)


# --------------------------------------------------------------------------
# Duplicate keys
# --------------------------------------------------------------------------


class _DuplicateDetectingLoader(yaml.SafeLoader):
    """A loader that records duplicate mapping keys instead of discarding them.

    PyYAML keeps the last of a repeated key without complaining. That is how
    AlignBeam.yaml came to define Feedback_good twice - once for XBPM1 and once
    for XBPM2 - leaving XBPM1 unread and unchecked while the report showed a
    single row that staff believed covered both.
    """

    duplicates = []


def _mapping_with_duplicate_check(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            _DuplicateDetectingLoader.duplicates.append(key)
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_DuplicateDetectingLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping_with_duplicate_check
)


def _yaml_files():
    found = []
    for module_name in sorted(os.listdir(MODULES_DIR)):
        module_dir = os.path.join(MODULES_DIR, module_name)
        if not os.path.isdir(module_dir):
            continue
        for entry in sorted(os.listdir(module_dir)):
            if entry.endswith(".yaml"):
                found.append(f"{module_name}/{entry}")
    return found


@pytest.mark.parametrize("relative_path", _yaml_files())
def test_no_duplicate_keys_in_module_yaml(relative_path):
    _DuplicateDetectingLoader.duplicates = []
    with open(os.path.join(MODULES_DIR, relative_path)) as handle:
        yaml.load(handle, Loader=_DuplicateDetectingLoader)
    assert not _DuplicateDetectingLoader.duplicates, (
        f"{relative_path} defines these keys more than once, so all but the last "
        f"are silently discarded: {sorted(set(_DuplicateDetectingLoader.duplicates))}"
    )


# --------------------------------------------------------------------------
# Every rule should be describable in the report's criterion column (F7)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,path,rules", RULE_BLOCKS, ids=[b[0] for b in RULE_BLOCKS]
)
def test_every_rule_has_a_criterion_string(assessor, label, path, rules):
    for name, rule in rules.items():
        if assessor.validate_assessment_rule(name, rule or {}):
            continue  # covered by the well-formed test
        assert assessor.describe_criterion(rule), f"{label}: {name} has no criterion"


# --------------------------------------------------------------------------
# V11 - which PVs are read as text
# --------------------------------------------------------------------------


@pytest.mark.parametrize("relative_path", _yaml_files())
def test_string_pvs_all_exist(relative_path):
    """Every name in string_pvs must be a PV the module actually reads.

    A stale name here is silent: the PV it was meant to protect goes back to
    being read raw, and an enum comes through as its index instead of its label.
    """
    with open(os.path.join(MODULES_DIR, relative_path)) as handle:
        config = yaml.safe_load(handle) or {}
    declared = config.get("string_pvs")
    if not declared:
        return
    known = {name for block in (config.get("PVs") or {}).values() for name in block}
    unknown = sorted(set(declared) - known)
    assert not unknown, f"{relative_path}: string_pvs names no such PV: {unknown}"


# --------------------------------------------------------------------------
# Report keys read by one module and written by another
# --------------------------------------------------------------------------


def test_emailready_reads_report_keys_that_exist():
    """EmailReady pulls values out of the TestCrystal report by name.

    Renaming a parameter in TestCrystal silently emptied the user email until
    2026-08-31: Aimless_Rmeas became Aimless_Rmeas_low_res and nothing failed,
    the email just stopped quoting an Rmeas. Cross-module reads by string key
    have no other guard, so this test names them explicitly.
    """
    import re

    from conftest import MODULES_DIR

    source = open(os.path.join(MODULES_DIR, "EmailReady", "EmailReady.py")).read()
    match = re.search(r"raw_rmeas = report_value\(([^)]*)\)", source)
    assert match, "EmailReady no longer fetches Rmeas the way this test expects"
    names = re.findall(r'"([^"]+)"', match.group(1))
    assert names == ["Aimless_Rmeas_low_res"], (
        "EmailReady reads only today's report, written by today's code, so it "
        "should name exactly the current key - historical reports are renamed by "
        "the migration tool rather than accommodated with fallbacks here"
    )

    quality_control = open(
        os.path.join(MODULES_DIR, "TestCrystal", "QualityControl.py")
    ).read()
    produced = set(re.findall(r'"(\w+)":\s*\("(\w+)"', quality_control)) | set(
        re.findall(r'"(\w+)",', quality_control)
    )
    produced = {
        name
        for pair in produced
        for name in (pair if isinstance(pair, tuple) else (pair,))
    }

    assert any(
        name in produced for name in names
    ), f"EmailReady reads {names}, none of which TestCrystal produces any more"
