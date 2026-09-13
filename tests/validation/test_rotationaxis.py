"""RotationAxis rules, against the module's real YAML."""

import pytest

from conftest import load_module_yaml


@pytest.fixture(scope="module")
def config():
    return load_module_yaml("RotationAxis")


@pytest.fixture(scope="module")
def rules(config):
    return config["assessment_rules"]


def test_popup_and_report_share_one_smargon_threshold(config, rules):
    """V5: the popup used 6 hours while the report row used 8, so between the two
    the popup warned and the report said good."""
    popup_hours = config["smargon_home_age_check"]["max_age"]["value"]
    assert popup_hours == rules["Smargon_home"]["limits"][0]


def test_smargon_home_is_read_as_text(config):
    """HOMESTATUS_MSG holds a formatted timestamp, which time_since parses."""
    assert "Smargon_home" in config["string_pvs"]


def test_positions_are_not_read_as_text(config):
    """V11: reading a position through as_string rounds it to display precision,
    which would hide changes these rules are meant to catch at the 0.001 level."""
    string_pvs = set(config.get("string_pvs", []))
    for name in ("STUB_X", "STUB_Y", "STUB_Z", "GONP_X", "GONP_Y", "GONP_Z"):
        assert name not in string_pvs


@pytest.mark.parametrize(
    "change,expected",
    [(0.0005, "good"), (0.001, "good"), (0.002, "warning"), (0.004, "danger")],
)
def test_stub_offset_change_bands(assessor, rules, change, expected):
    assert (
        assessor.assess_deadband(
            1.0 + change, 1.0, rules["STUB_X"]["limits"], "absolute"
        )
        == expected
    )


@pytest.mark.parametrize(
    "value,expected",
    [(0.00005, "good"), (0.0001, "good"), (0.0003, "warning"), (0.001, "danger")],
)
def test_gonp_x_must_sit_near_zero(assessor, rules, value, expected):
    assert assessor.assess_in_range(value, rules["GONP_X"]["limits"]) == expected
