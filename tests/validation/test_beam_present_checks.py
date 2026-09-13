"""AlignBeam refuses to photograph a beamline that has nothing to show (F12).

`checks()` carried this for a long time:

    CRITICAL FIXME - I am not checking for shutter opened, scintillator up and
    flux is okish!!

and returned True regardless. So the module could step the zoom through eight
levels photographing a dark field and report it as a beam alignment. Obvious to a
person looking at the images, which is why it survived; invisible to the
assessment.
"""

import logging
import os

import pytest

from conftest import REPO_ROOT, load_module_yaml


@pytest.fixture
def checker():
    from modules.AlignBeam.AlignBeam import OpticsChecks

    class Fake:
        BEAM_PRESENT_CHECKS = OpticsChecks.BEAM_PRESENT_CHECKS

        def __init__(self):
            self.log = logging.getLogger("beam-present-tests")

    Fake.checks = OpticsChecks.__dict__["checks"]
    return Fake()


def assessed(**statuses):
    return {
        name: {"status": status, "display": name} for name, status in statuses.items()
    }


READY = dict(
    Scintillator_Y="good", Endstation_shutter="good", Fast_shutter="good", FLUX="good"
)


def test_a_ready_beamline_passes(checker):
    assert checker.checks(assessed(**READY)) is True


@pytest.mark.parametrize(
    "broken,why",
    [
        ("Scintillator_Y", "the scintillator is out of the beam"),
        ("Endstation_shutter", "the endstation shutter is shut"),
        ("Fast_shutter", "the fast shutter is shut"),
        ("FLUX", "there is no beam"),
    ],
)
def test_any_one_of_them_stops_it(checker, broken, why):
    states = dict(READY)
    states[broken] = "danger"
    assert checker.checks(assessed(**states)) is False, why
    assert any(broken in reason for reason in checker.not_ready_reasons)


def test_the_reasons_are_collected_not_just_the_first(checker):
    """The operator should learn everything that is wrong in one go."""
    states = dict(READY, Endstation_shutter="danger", Fast_shutter="danger")
    checker.checks(assessed(**states))
    assert len(checker.not_ready_reasons) == 2


def test_a_warning_does_not_stop_it(checker):
    """A scintillator part way is worth flagging, not worth refusing over -
    that is the difference between the warning and danger bands."""
    states = dict(READY, Scintillator_Y="warning")
    assert checker.checks(assessed(**states)) is True


def test_missing_parameters_do_not_block(checker):
    """A beamline without one of these devices omits the rule, and the check
    disappears with it rather than failing closed."""
    assert checker.checks(assessed(FLUX="good")) is True


def test_no_parameters_at_all_does_not_block(checker):
    assert checker.checks(None) is True
    assert checker.checks({}) is True


# --------------------------------------------------------------------------
# The configuration behind it
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def config():
    return load_module_yaml("AlignBeam")


def test_the_pvs_and_rules_exist(config):
    rules = config["assessment_rules"]
    assert rules["Endstation_shutter"]["good_value"] == "Open"
    assert rules["Fast_shutter"]["good_value"] == "Open"
    assert rules["Scintillator_Y"]["check_type"] == "greater_than"


def test_the_shutters_are_read_as_text(config):
    """They are enums; read raw they would come back as an index."""
    for name in ("Endstation_shutter", "Fast_shutter"):
        assert name in config["string_pvs"]


def test_none_of_them_clutter_the_report(config):
    """Whether there is beam is clear from the image; three rows saying Open
    every morning would be noise."""
    for name in ("Scintillator_Y", "Endstation_shutter", "Fast_shutter"):
        assert name in config["hidden_parameters"]


@pytest.mark.parametrize(
    "y,expected",
    [
        (-0.44937, "danger"),  # the live reading while out, 2026-08-31
        (-1.0, "danger"),  # the older SCIN_OUT setpoint
        (45.0, "warning"),  # stopped part way
        (93.42, "good"),  # the oldest SCIN_IN in beamlineParameters
        (96.35, "good"),  # the current one
        (97.45, "good"),  # the highest recorded
    ],
)
def test_the_scintillator_threshold_survives_retuning(assessor, config, y, expected):
    """The setpoints are retuned from time to time - nine different in positions
    are recorded in beamlineParameters - so the threshold sits in the 97 mm gap
    between in and out rather than near either value."""
    limits = config["assessment_rules"]["Scintillator_Y"]["limits"]
    assert assessor.assess_greater_than(y, limits) == expected


def test_the_fixme_is_gone():
    source = open(
        os.path.join(REPO_ROOT, "modules", "AlignBeam", "AlignBeam.py")
    ).read()
    assert (
        "FIXME" not in source
    ), "the note said these checks were missing; they are not missing any more"
