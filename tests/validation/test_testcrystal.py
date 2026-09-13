"""TestCrystal rules, against the module's real YAML."""

import os

import pytest

from conftest import load_module_yaml


@pytest.fixture(scope="module")
def rules():
    return load_module_yaml("TestCrystal")["assessment_rules"]


# Dose does not come from a processing log. It is joined onto the report from the
# eiger arming log and the RADDOSE-3D service by TestCrystal.collect_dose, so the
# parser knows nothing about it - see base/dose.py.
MODULE_SUPPLIED = {
    "Dose_this_collection_MGy",
    "Dose_crystal_lifetime_MGy",
    "Dose_collections_counted",
}


def test_every_rule_has_a_parsed_source(rules):
    """Each assessed parameter must be something that actually reaches the report.

    Almost all of them come from a processing log via the parser. The exception is
    dose, which the module joins on from another source; those are listed above
    rather than exempted by a pattern, so a typo in a new rule still fails here.
    """
    import sys, os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from test_qualitycontrol_parser import Parser

    for name in rules:
        if name in MODULE_SUPPLIED:
            continue
        assert name in Parser.REPORT_FIELDS, f"{name} is assessed but never parsed"


def test_the_module_really_produces_the_parameters_it_is_excused_for():
    """The exemption above must not become a place to hide a dead rule."""
    from conftest import REPO_ROOT

    source = open(
        os.path.join(REPO_ROOT, "modules", "TestCrystal", "TestCrystal.py")
    ).read()
    for name in MODULE_SUPPLIED - {"Dose_collections_counted"}:
        assert (
            f'"{name}"' in source
        ), f"{name} is exempted from the parser check but nothing writes it"


def test_no_duplicate_measurements_are_assessed(rules):
    """V10: the summary block showed ten rows for five measurements.

    Each measurement must be assessed once. Both resolutions and all three
    R-factor variants came from the same aimless run, so only one of each
    survives; the per-image diagnostics are separate measurements, not copies.
    """
    duplicated = {
        "Aimless_Resolution",
        "Rmerge_low_res",
        "Aimless_Rmerge_low_res",
        "Aimless_CChalf",
        "Aimless_Completeness",
    }
    assert not duplicated & set(rules)
    assert {"Resolution", "Aimless_Rmeas_low_res", "CChalf", "Completeness"} <= set(
        rules
    )


@pytest.mark.parametrize(
    "isa,expected",
    [
        (41.0, "good"),
        (35.0, "good"),
        (30.0, "warning"),
        (25.0, "warning"),
        (3.51, "danger"),
    ],
)
def test_isa_bands(assessor, rules, isa, expected):
    """3.51 is the lowest ISa in 186 recorded reports, on 2026-08-11."""
    assert assessor.assess_greater_than(isa, rules["ISa"]["limits"]) == expected


@pytest.mark.parametrize(
    "resolution,expected",
    [
        (1.26, "good"),
        (2.0, "good"),
        (2.04, "warning"),
        (2.5, "warning"),
        (2.6, "danger"),
    ],
)
def test_resolution_bands(assessor, rules, resolution, expected):
    assert (
        assessor.assess_less_than(resolution, rules["Resolution"]["limits"]) == expected
    )


def test_resolution_warning_band_is_reachable(assessor, rules):
    """The reversed-limits defect made this band impossible to reach."""
    statuses = {
        assessor.assess_less_than(v, rules["Resolution"]["limits"])
        for v in (1.0, 2.04, 2.3, 2.6)
    }
    assert "warning" in statuses


@pytest.mark.parametrize(
    "rmeas,expected",
    [(0.020, "good"), (0.030, "good"), (0.034, "warning"), (0.161, "danger")],
)
def test_rmeas_low_resolution_bands(assessor, rules, rmeas, expected):
    assert (
        assessor.assess_less_than(rmeas, rules["Aimless_Rmeas_low_res"]["limits"])
        == expected
    )
