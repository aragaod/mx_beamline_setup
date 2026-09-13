"""AlignBeam rules, exercised against the module's real YAML.

These run the shipped ``modules/AlignBeam/AlignBeam.yaml`` rather than a fixture,
so a limit edited in the YAML shows up here. Statuses are recomputed from values,
never read back from redis, because a stored status reflects whatever limits were
in force on the day it was written.
"""

import pytest

from conftest import load_module_yaml


@pytest.fixture(scope="module")
def rules():
    return load_module_yaml("AlignBeam")["assessment_rules"]


@pytest.fixture(scope="module")
def pv_map():
    return load_module_yaml("AlignBeam")["PVs"]


# --------------------------------------------------------------------------
# V2 - both beam position monitors must be checked
# --------------------------------------------------------------------------


def test_both_xbpm_feedback_pvs_are_read(pv_map):
    """AlignBeam.yaml used to name Feedback_good twice, so XBPM1 was dropped."""
    feedback = pv_map["BL04I-EA-FDBK-01"]
    assert feedback["Feedback_XBPM1_good"] == "XBPM1POSITION_OK"
    assert feedback["Feedback_XBPM2_good"] == "XBPM2POSITION_OK"


def test_both_xbpm_feedback_pvs_are_assessed(rules):
    assert "Feedback_XBPM1_good" in rules
    assert "Feedback_XBPM2_good" in rules


# --------------------------------------------------------------------------
# V1 - flux
# --------------------------------------------------------------------------


def test_flux_rule_has_two_limits(rules):
    """A single limit made assess_deadband raise, which reported danger forever."""
    assert len(rules["FLUX"]["limits"]) == 2


@pytest.mark.parametrize(
    "flux,transmission,expected",
    [
        # Same beam, different working transmission: normalising must cancel it.
        (2.00e11, 20.0, "good"),
        (6.00e10, 6.0, "good"),
        (2.50e11, 25.0, "good"),
        # A real 15% drop at unchanged transmission.
        (1.70e11, 20.0, "warning"),
        # A real halving.
        (1.00e11, 20.0, "danger"),
    ],
)
def test_flux_normalised_before_comparison(
    assessor, rules, flux, transmission, expected
):
    """Yesterday: 2.00e11 at 20% transmission, i.e. 1.00e12 at 100%."""
    previous = 2.00e11 / 20.0 * 100
    current = flux / transmission * 100
    assert (
        assessor.assess_deadband(current, previous, rules["FLUX"]["limits"], "percent")
        == expected
    )


def test_flux_at_full_beam_is_comparable_with_a_low_transmission_day(assessor, rules):
    """The 100% transmission days are the ones the old check spiked on."""
    yesterday = 6.00e10 / 6.0 * 100  # 1.00e12
    today = 1.05e12 / 100.0 * 100  # 1.05e12
    assert (
        assessor.assess_deadband(today, yesterday, rules["FLUX"]["limits"], "percent")
        == "good"
    )


# --------------------------------------------------------------------------
# V7 - beam size
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "horizontal,vertical,expected",
    [
        (30.0, 19.0, "good"),  # 177 of 191 recorded setups
        (31.0, 20.0, "warning"),  # slightly off: energy not where it should be
        (43.0, 30.0, "danger"),  # a different CRL setting
        (62.0, 48.0, "danger"),
    ],
)
def test_beam_size_pairs(assessor, rules, horizontal, vertical, expected):
    assert (
        assessor.assess_in_range(horizontal, rules["BEAM_SIZE_X"]["limits"]) == expected
    )
    assert (
        assessor.assess_in_range(vertical, rules["BEAM_SIZE_Y"]["limits"]) == expected
    )


# --------------------------------------------------------------------------
# V9 - full-beam alignment is an error, and must stay one
# --------------------------------------------------------------------------


def test_full_transmission_during_alignment_is_danger(assessor, rules):
    """Aligning at 100% saturates the camera and scintillator, so the centre the
    staff member picks may not be the real one. This must not be relaxed."""
    assert assessor.assess_in_range(100.0, rules["TRANSMISSION"]["limits"]) == "danger"


@pytest.mark.parametrize("transmission", [6.0, 15.0, 20.0, 25.0, 35.0])
def test_normal_working_transmissions_are_good(assessor, rules, transmission):
    assert (
        assessor.assess_in_range(transmission, rules["TRANSMISSION"]["limits"])
        == "good"
    )


# --------------------------------------------------------------------------
# The engine end to end, on a realistic parameter set
# --------------------------------------------------------------------------


def test_engine_marks_no_history_rather_than_passing(assessor, rules):
    """With no previous report the deadband rules must not silently say good."""
    result = assessor.assess_parameters(
        {"DCM_roll": 6.69, "Machine_X_STEER": -2.0}, rules, {}, where="AlignBeam"
    )
    for name in ("DCM_roll", "Machine_X_STEER"):
        assert "status" not in result[name]
        assert "no previous report" in result[name]["note"]


def test_engine_attaches_a_criterion_to_every_assessed_row(assessor, rules):
    result = assessor.assess_parameters(
        {"BEAM_SIZE_X": 30.0, "TRANSMISSION": 20.0}, rules, {}, where="AlignBeam"
    )
    assert result["BEAM_SIZE_X"]["criterion"]
    assert result["TRANSMISSION"]["criterion"]


# --------------------------------------------------------------------------
# V4 - PID feedback gains
# --------------------------------------------------------------------------


def test_dcm_x_gain_uses_an_absolute_ceiling(rules):
    """Change detection alone is not enough: the aggressive value must be red."""
    rule = rules["PID_XBPM1_X_KP"]
    assert rule["check_type"] == "abs_limit_and_change"
    assert rule["limits"][1] <= 1.0e-5


@pytest.mark.parametrize(
    "current,previous,expected",
    [
        (6e-06, 6e-06, "good"),
        (7e-06, 6e-06, "warning"),
        (1e-05, 6e-06, "danger"),
        (1e-05, 1e-05, "danger"),
    ],
)
def test_dcm_x_gain_statuses(assessor, rules, current, previous, expected):
    assert (
        assessor.assess_abs_limit_and_change(
            current, previous, rules["PID_XBPM1_X_KP"]["limits"]
        )
        == expected
    )


def test_live_dcm_x_gain_would_be_flagged(assessor, rules):
    """The value read from the beamline on 2026-08-31 was 1e-05.

    Recorded as a test so that if anyone ever widens this limit, it is obvious
    that the reading which prompted the check would stop being caught.
    """
    assert (
        assessor.assess_abs_limit_and_change(
            1e-05, 7e-06, rules["PID_XBPM1_X_KP"]["limits"]
        )
        == "danger"
    )


@pytest.mark.parametrize("name", ["PID_XBPM1_Y_KP", "PID_XBPM2_X_KP", "PID_XBPM2_Y_KP"])
def test_other_gains_detect_change(assessor, rules, name):
    """Interim until the diagnostics group supplies a ceiling for these loops."""
    assert rules[name]["check_type"] == "equals_previous"
    assert assessor.assess_equals_previous(-2e-05, -2e-05) == "good"
    assert assessor.assess_equals_previous(-4e-05, -2e-05) == "warning"
