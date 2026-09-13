"""Boundary tests for the assessment helpers on ``base.Modules.Base``.

These are pure functions, so they are the cheapest and highest-value tests in the
suite. Each check is exercised *on* its limits as well as either side, because
the defects these tests exist to prevent were all boundary or arity mistakes:

  * V1  a one-element ``limits`` list turned every flux reading into "danger"
  * V3  a reversed ``less_than`` pair made the warning band unreachable
  * V8  nothing validated that ``limits`` matched the check type
"""

import pytest


# --------------------------------------------------------------------------
# assess_greater_than: limits are [good_if_above, warning_if_above]
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (1.2e12, "good"),
        (9.0e11, "good"),  # exactly on the good limit
        (8.9e11, "warning"),
        (7.0e11, "warning"),  # exactly on the warning limit
        (6.9e11, "danger"),
        (0.0, "danger"),
    ],
)
def test_flux_absolute_boundaries(assessor, value, expected):
    assert assessor.assess_greater_than(value, [9.0e11, 7.0e11]) == expected


# --------------------------------------------------------------------------
# assess_less_than: limits are [good_if_below, warning_if_below]
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (1.8, "good"),
        (2.0, "good"),  # exactly on the good limit
        (2.1, "warning"),
        (2.5, "warning"),  # exactly on the warning limit
        (2.6, "danger"),
    ],
)
def test_resolution_boundaries(assessor, value, expected):
    assert assessor.assess_less_than(value, [2.0, 2.5]) == expected


def test_resolution_reversed_limits_can_never_warn(assessor):
    """The V3 defect, pinned so it cannot come back unnoticed.

    With [2.5, 2.0] every value is good or danger and the warning band is
    unreachable. The arithmetic is not wrong - the configuration is - which is
    why validate_assessment_rule has to catch it instead.
    """
    statuses = {
        assessor.assess_less_than(v, [2.5, 2.0]) for v in (1.0, 2.2, 2.5, 2.6, 3.0)
    }
    assert "warning" not in statuses


# --------------------------------------------------------------------------
# assess_in_range: [good_min, good_max, warn_min, warn_max]
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (30.0, "good"),
        (29.5, "good"),
        (30.5, "good"),
        (31.0, "warning"),
        (28.5, "warning"),
        (32.5, "warning"),
        (33.0, "danger"),
        (43.0, "danger"),  # a different CRL setting
    ],
)
def test_beam_size_x_bands(assessor, value, expected):
    assert assessor.assess_in_range(value, [29.5, 30.5, 28.5, 32.5]) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(19.0, "good"), (20.0, "warning"), (18.0, "warning"), (9.0, "danger")],
)
def test_beam_size_y_bands(assessor, value, expected):
    assert assessor.assess_in_range(value, [18.5, 19.5, 17.5, 20.5]) == expected


# --------------------------------------------------------------------------
# assess_deadband
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "current,expected",
    [
        (1.00e12, "good"),  # no change
        (1.10e12, "good"),  # exactly 10%
        (1.15e12, "warning"),
        (1.20e12, "warning"),  # exactly 20%
        (1.21e12, "danger"),
        (0.50e12, "danger"),  # a halving is a danger, not a pass
    ],
)
def test_flux_drift_bands(assessor, current, expected):
    assert assessor.assess_deadband(current, 1.00e12, [10, 20], "percent") == expected


def test_deadband_with_no_previous_is_not_good(assessor):
    """Not assessable is not the same as passing - this must be None, not 'good'."""
    assert assessor.assess_deadband(1.0, None, [10, 20], "percent") is None


def test_machine_steer_zero_deadband_flags_any_change(assessor):
    assert assessor.assess_deadband(-2.0, -2.0, [0, 2], "absolute") == "good"
    assert assessor.assess_deadband(-1.0, -2.0, [0, 2], "absolute") == "warning"
    assert assessor.assess_deadband(2.0, -2.0, [0, 2], "absolute") == "danger"


# --------------------------------------------------------------------------
# assess_abs_limit_and_change: the PID gain check (V4)
# --------------------------------------------------------------------------

PID_LIMITS = [8.0e-6, 9.9e-6]


@pytest.mark.parametrize(
    "current,previous,expected,why",
    [
        (6e-06, 6e-06, "good", "unchanged and well within the safe range"),
        (7e-06, 6e-06, "warning", "a small retune is noticed but not alarming"),
        (5e-06, 6e-06, "warning", "downward retunes are noticed too"),
        (1e-05, 6e-06, "danger", "the aggressive value that oscillates at low energy"),
        (1e-05, 1e-05, "danger", "still aggressive even if nobody touched it today"),
        (-1e-05, -6e-06, "danger", "the sign does not matter, the magnitude does"),
        (9e-06, 9e-06, "warning", "above the good limit but not yet dangerous"),
    ],
)
def test_pid_gain_absolute_and_change(assessor, current, previous, expected, why):
    assert assessor.assess_abs_limit_and_change(current, previous, PID_LIMITS) == (
        expected
    ), why


# --------------------------------------------------------------------------
# Bad input must never be reported as a beamline fault
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, "", "not-a-number", [], {}])
def test_helpers_do_not_crash_on_rubbish(assessor, bad):
    for call in (
        lambda: assessor.assess_greater_than(bad, [1, 2]),
        lambda: assessor.assess_less_than(bad, [1, 2]),
        lambda: assessor.assess_in_range(bad, [1, 2, 3, 4]),
        lambda: assessor.assess_deadband(bad, 1.0, [1, 2], "percent"),
    ):
        assert call() in ("good", "warning", "danger", None)


# --------------------------------------------------------------------------
# F7 - the criterion string shown beside each row in the report
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule,expected",
    [
        ({"check_type": "greater_than", "limits": [9.0e11, 7.0e11]}, ">= 9e+11"),
        ({"check_type": "less_than", "limits": [2.0, 2.5]}, "<= 2"),
        ({"check_type": "in_range", "limits": [29.5, 30.5, 28.5, 32.5]}, "29.5-30.5"),
        ({"check_type": "equals", "good_value": "Run"}, "= Run"),
        ({"check_type": "equals_previous"}, "= yesterday"),
        (
            {"check_type": "deadband_percent", "limits": [10, 20]},
            "delta <= 10% vs yest",
        ),
        # A zero deadband is change detection, not a tolerance.
        ({"check_type": "deadband_absolute", "limits": [0, 2]}, "= yesterday"),
        (
            {"check_type": "deadband_absolute", "limits": [0.5, 1.0]},
            "delta <= 0.5 vs yest",
        ),
        ({"check_type": "time_since", "limits": [8, 18]}, "< 8 h ago"),
    ],
)
def test_criterion_strings(assessor, rule, expected):
    assert assessor.describe_criterion(rule) == expected


def test_criterion_includes_the_default_for_a_pid_gain(assessor):
    rule = {
        "check_type": "abs_limit_and_change",
        "limits": [8.0e-6, 1.0e-5],
        "default": 6.0e-6,
    }
    criterion = assessor.describe_criterion(rule)
    assert "6e-06" in criterion, "the recovery value must be visible in the report"
    assert "= yest" in criterion


def test_unknown_check_type_has_no_criterion_and_does_not_raise(assessor):
    assert assessor.describe_criterion({"check_type": "nonsense"}) == ""


# --------------------------------------------------------------------------
# V11 - raw values are stored, formatted values are displayed
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,shown",
    [
        (19.999984741210938, "20"),  # a transmission of exactly 20%
        (0.000108, "0.000108"),  # a PID gain as_string would round to 0.00011
        (-5.67e-05, "-5.67e-05"),
        (1e-05, "1e-05"),
        (30.0, "30"),
        ("Run", "Run"),  # text passes through untouched
    ],
)
def test_display_formatting(assessor, raw, shown):
    assert assessor.format_value(raw) == shown


def test_stored_value_stays_raw_for_tomorrows_comparison(assessor):
    """The report shows `display`; `value` must keep full precision."""
    rules = {"DCMP_temp1": {"check_type": "deadband_percent", "limits": [2, 5]}}
    result = assessor.assess_parameters(
        {"DCMP_temp1": 19.999984741210938}, rules, {"DCMP_temp1": 20.0}
    )
    assert result["DCMP_temp1"]["value"] == 19.999984741210938
    assert result["DCMP_temp1"]["display"] == "20"


# --------------------------------------------------------------------------
# assess_equals_previous across a change in how values are stored
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "current,previous,expected,why",
    [
        (-6e-05, "-0.00006", "good", "same number, written differently"),
        (0.00011, "0.00011", "good", "same number, same text"),
        (
            -5.67e-05,
            "-0.00006",
            "warning",
            "genuinely different once precision is kept",
        ),
        (-4e-05, -6e-05, "warning", "a real change, both numeric"),
        (".5 second", ".5 second", "good", "text values still compare as text"),
        (".2 second", ".5 second", "warning", "and still detect a change"),
        ("Run", "Run", "good", "non-numeric text is unaffected"),
    ],
)
def test_equals_previous_survives_a_change_of_stored_format(
    assessor, current, previous, expected, why
):
    """V11 changed numeric PVs from display strings to raw floats, so on the first
    run after it every comparison has a float on one side and a string on the
    other. A string-only comparison reports every one of those as a change.
    """
    assert assessor.assess_equals_previous(current, previous) == expected, why


def test_deadband_already_coped_with_string_history(assessor):
    """The deadband family coerces with float(), so it was never affected."""
    assert assessor.assess_deadband(-2.0, "-2.00", [0, 2], "absolute") == "good"
    assert assessor.assess_deadband(-192.3, "-192.3", [2, 5], "percent") == "good"


def test_a_renamed_parameter_reports_no_history_rather_than_an_alarm(assessor):
    """Renaming a key means yesterday's report has no such parameter.

    That must read as "not compared yet", not as a change - which is what the
    no-history policy already gives.
    """
    result = assessor.assess_parameters(
        {"Rmerge_low_res": 0.034},
        {
            "Rmerge_low_res": {
                "check_type": "deadband_absolute",
                "limits": [0.001, 0.003],
            }
        },
        {"Rmerge": 0.034},  # yesterday, under the old name
    )
    assert "status" not in result["Rmerge_low_res"]
    assert "no previous report" in result["Rmerge_low_res"]["note"]
