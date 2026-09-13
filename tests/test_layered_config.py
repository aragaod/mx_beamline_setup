"""The layered-YAML resolver.

One shared default per module, plus an optional per-beamline override merged over
it:

    RotationAxis.yaml         what the check is - beamline independent
    RotationAxis.i04.yaml     i04's PVs, paths and thresholds
    RotationAxis.i04-1.yaml   i04-1's, when it exists

The requirement that makes this more than a dict merge: an override must be able
to **remove** a check, not only re-value one. i04-1 has a goniometer rather than a
smargon, so its RotationAxis override has to delete smargon_home_age_check and the
STUB_* rules outright.
"""

import os

import pytest
import yaml

from base.GUI_Modules_Base import deep_merge, substitute_beamline


# --------------------------------------------------------------------------
# deep_merge
# --------------------------------------------------------------------------


def test_override_replaces_a_scalar():
    assert deep_merge({"width": 800}, {"width": 1000}) == {"width": 1000}


def test_override_adds_a_key():
    assert deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_nested_dictionaries_merge_rather_than_replace():
    """Overriding one limit must not delete the other rules in the block."""
    base = {
        "assessment_rules": {
            "STUB_X": {"check_type": "deadband_absolute", "limits": [0.001, 0.003]},
            "GONP_X": {"check_type": "in_range", "limits": [-1, 1, -2, 2]},
        }
    }
    override = {"assessment_rules": {"STUB_X": {"limits": [0.01, 0.03]}}}
    merged = deep_merge(base, override)
    assert merged["assessment_rules"]["STUB_X"]["limits"] == [0.01, 0.03]
    assert merged["assessment_rules"]["STUB_X"]["check_type"] == "deadband_absolute"
    assert "GONP_X" in merged["assessment_rules"], "untouched rules must survive"


def test_a_null_override_removes_the_key():
    """The i04-1 case: no smargon, so the check must disappear entirely."""
    base = {"smargon_home_age_check": {"enabled": True}, "report_table_title": "x"}
    merged = deep_merge(base, {"smargon_home_age_check": None})
    assert "smargon_home_age_check" not in merged
    assert merged["report_table_title"] == "x"


def test_a_null_override_removes_a_nested_rule():
    base = {
        "assessment_rules": {"STUB_X": {"limits": [1, 2]}, "GONP_X": {"limits": [3]}}
    }
    merged = deep_merge(base, {"assessment_rules": {"STUB_X": None}})
    assert set(merged["assessment_rules"]) == {"GONP_X"}


def test_lists_replace_wholesale():
    """A limits list must be stated in full, not merged element by element."""
    merged = deep_merge({"limits": [1, 2, 3, 4]}, {"limits": [9, 9]})
    assert merged["limits"] == [9, 9]


def test_removing_a_missing_key_is_not_an_error():
    assert deep_merge({"a": 1}, {"b": None}) == {"a": 1}


def test_the_base_is_not_mutated():
    base = {"nested": {"value": 1}}
    deep_merge(base, {"nested": {"value": 2}})
    assert base["nested"]["value"] == 1


# --------------------------------------------------------------------------
# {BEAMLINE} substitution
# --------------------------------------------------------------------------


def test_substitution_reaches_nested_strings():
    config = {
        "path": "/dls_sw/{BEAMLINE}/software",
        "nested": {"deep": ["/dls/{BEAMLINE}/data", 5]},
    }
    out = substitute_beamline(config, "i04-1")
    assert out["path"] == "/dls_sw/i04-1/software"
    assert out["nested"]["deep"][0] == "/dls/i04-1/data"
    assert out["nested"]["deep"][1] == 5, "non-strings pass through untouched"


def test_substitution_leaves_other_text_alone():
    assert substitute_beamline("no placeholder here", "i04") == "no placeholder here"


# --------------------------------------------------------------------------
# The real module YAMLs, resolved
# --------------------------------------------------------------------------

from conftest import MODULES_DIR


def _module_stems():
    found = []
    for module in sorted(os.listdir(MODULES_DIR)):
        directory = os.path.join(MODULES_DIR, module)
        if not os.path.isdir(directory):
            continue
        for entry in sorted(os.listdir(directory)):
            if entry.endswith(".yaml") and entry.count(".") == 1:
                found.append((module, entry[:-5]))
    return found


def resolve(module, stem, beamline="i04"):
    directory = os.path.join(MODULES_DIR, module)
    with open(os.path.join(directory, f"{stem}.yaml")) as handle:
        config = yaml.safe_load(handle) or {}
    override_path = os.path.join(directory, f"{stem}.{beamline}.yaml")
    if os.path.exists(override_path):
        with open(override_path) as handle:
            config = deep_merge(config, yaml.safe_load(handle) or {})
    return substitute_beamline(config, beamline)


@pytest.mark.parametrize(
    "module,stem", _module_stems(), ids=[m for m, _ in _module_stems()]
)
def test_every_module_resolves(module, stem):
    config = resolve(module, stem)
    assert config, f"{module}/{stem} resolved to nothing"


@pytest.mark.parametrize(
    "module,stem", _module_stems(), ids=[m for m, _ in _module_stems()]
)
def test_no_beamline_placeholder_survives_resolution(module, stem):
    """A path that still says {BEAMLINE} after resolution would be used literally.

    Modules used to each call .format(BEAMLINE=...) on the paths they happened to
    remember, so this is exactly the bug the shared substitution removes.
    """
    text = repr(resolve(module, stem))
    assert "{BEAMLINE}" not in text


@pytest.mark.parametrize(
    "module,stem", _module_stems(), ids=[m for m, _ in _module_stems()]
)
def test_shared_file_holds_no_i04_addresses(module, stem):
    """The shared default must be beamline independent.

    An EPICS prefix or a hardcoded /dls_sw/i04 path left in the shared file is
    the whole problem the split exists to fix: another beamline reading that file
    would silently talk to i04's hardware.
    """
    with open(os.path.join(MODULES_DIR, module, f"{stem}.yaml")) as handle:
        shared = handle.read()
    # Strip comments; they legitimately mention i04 when explaining a measurement.
    body = "\n".join(
        line for line in shared.splitlines() if not line.strip().startswith("#")
    )
    assert "BL04I-" not in body, f"{module}/{stem}.yaml still holds an i04 EPICS prefix"
    assert "/dls_sw/i04/" not in body, f"{module}/{stem}.yaml still holds an i04 path"


def test_a_beamline_without_a_smargon_can_drop_those_checks():
    """The i04-1 case, end to end: goniometer not smargon, so no homing check.

    This is why deep_merge honours nulls. i04-1 does not need a mapping layer for
    the smargon, it needs to be able to say "that check does not exist here".
    """
    shared = resolve("RotationAxis", "RotationAxis")
    assert "smargon_home_age_check" in shared, "i04 must still have it"

    hypothetical_i04_1 = {
        "smargon_home_age_check": None,
        "assessment_rules": {
            "STUB_X": None,
            "STUB_Y": None,
            "STUB_Z": None,
            "Smargon_home": None,
        },
        "PVs": {"BL24I-MO-GONIO-01": {"GONP_X": "X.RBV"}},
    }
    merged = deep_merge(shared, hypothetical_i04_1)
    assert "smargon_home_age_check" not in merged
    assert not {"STUB_X", "STUB_Y", "STUB_Z", "Smargon_home"} & set(
        merged["assessment_rules"]
    )
    assert "GONP_X" in merged["assessment_rules"], "the goniometer checks survive"


# --------------------------------------------------------------------------
# Wizard text is per-beamline too, not just PVs and limits
# --------------------------------------------------------------------------


def test_a_beamline_can_override_the_wizard_text():
    """Instructions diverge between beamlines, not only addresses and limits.

    Different hardware means a step may be done differently, or not at all, so an
    override must be able to replace the text staff read. The shared file holds
    the default wording; a beamline that needs different wording states it.
    """
    shared = resolve("RotationAxis", "RotationAxis")
    assert "WP1_Label_1_Text" in shared

    override = {"WP1_Label_1_Text": "Mount the pin. This beamline has no smargon.\n"}
    merged = deep_merge(shared, override)
    assert merged["WP1_Label_1_Text"] == override["WP1_Label_1_Text"]
    assert (
        merged["WP2_Label_1_Text"] == shared["WP2_Label_1_Text"]
    ), "overriding one page must not disturb the others"


def test_overriding_text_does_not_require_restating_the_title():
    """Text and title are separate keys, so a beamline can change just one."""
    shared = resolve("AlignBeam", "AlignBeam")
    merged = deep_merge(shared, {"WP1_Label_1_Text": "different instructions"})
    assert merged["WP1_Label_1_Title"] == shared["WP1_Label_1_Title"]


def test_report_table_title_can_differ_per_beamline():
    shared = resolve("TestCrystal", "TestCrystal")
    merged = deep_merge(shared, {"report_table_title": "i04-1 Diffraction Statistics"})
    assert merged["report_table_title"] == "i04-1 Diffraction Statistics"
