"""Recording the crosshair position (AlignBeam).

Nothing stored this before, so there is no history to backfill: it accumulates
from the first run after deployment. It is wanted for correlating crosshair
movement against the machine steering and beamstop realignment question.

Two properties matter beyond "it parses":

  * It must sit on the **safe** path. AlignBeam splits into collect_pv_data,
    which reads and assesses, and collect_image_data, which drives the zoom
    through all eight levels. Recording a number must never require driving the
    beamline - see the operating constraint at the top of PROGRESS.md.
  * It must not reach the eLog. It is a value kept for later analysis, not
    something staff need to read every morning.
"""

import logging
import os

import pytest

from conftest import REPO_ROOT, load_module_yaml

FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures"
)


@pytest.fixture
def collector():
    """The crosshair reader, unbound from EPICS and the GUI."""
    from modules.AlignBeam.AlignBeam import OpticsChecks

    class Fake:
        display_configuration_file = os.path.join(FIXTURES, "display.configuration")

        def __init__(self):
            self.log = logging.getLogger("crosshair-tests")

    for name in ("collect_crosshair_positions", "get_zoom_dict"):
        setattr(Fake, name, OpticsChecks.__dict__[name])
    return Fake()


def test_crosshair_positions_are_read_per_zoom_level(collector):
    positions = collector.collect_crosshair_positions()["Crosshair_positions"]
    assert sorted(positions, key=float) == ["1.0", "7.5", "10.0"]
    assert positions["7.5"] == {"x": 464, "y": 381}


def test_values_are_integers_not_strings(collector):
    """Stored raw, like every other numeric value since V11."""
    positions = collector.collect_crosshair_positions()["Crosshair_positions"]
    assert all(isinstance(v, int) for pos in positions.values() for v in pos.values())


def test_a_missing_configuration_file_does_not_break_the_module(collector):
    """A setup must still complete if the file is unreadable."""
    collector.display_configuration_file = "/nonexistent/display.configuration"
    assert collector.collect_crosshair_positions() == {}


def test_one_parameter_not_one_per_zoom_level(collector):
    """Which zoom levels exist is beamline-specific - i04 has 7.5x, i04-1 does
    not - so a per-zoom parameter name would put that difference into every
    report and into every per-beamline YAML."""
    got = collector.collect_crosshair_positions()
    assert list(got) == ["Crosshair_positions"]


# --------------------------------------------------------------------------
# It must be recorded, and must not be published
# --------------------------------------------------------------------------


def test_crosshair_is_declared_hidden():
    assert "Crosshair_positions" in load_module_yaml("AlignBeam")["hidden_parameters"]


def test_hidden_declaration_is_beamline_independent():
    """The parameter name is the same on any beamline, so it belongs in the
    shared file rather than the i04 override."""
    shared = open(
        os.path.join(REPO_ROOT, "modules", "AlignBeam", "AlignBeam.yaml")
    ).read()
    override = open(
        os.path.join(REPO_ROOT, "modules", "AlignBeam", "AlignBeam.i04.yaml")
    ).read()
    assert "hidden_parameters:" in shared
    assert "hidden_parameters:" not in override


def test_crosshair_is_stored_but_marked_hidden(assessor, collector):
    """Stored in redis, absent from the rendered table."""
    raw = collector.collect_crosshair_positions()
    result = assessor.assess_parameters(
        raw,
        {},
        {},
        where="AlignBeam",
        hidden=load_module_yaml("AlignBeam")["hidden_parameters"],
    )
    entry = result["Crosshair_positions"]
    assert entry["hidden"] is True
    assert entry["value"]["7.5"] == {"x": 464, "y": 381}, "the value is still there"


def test_collected_on_the_safe_path_not_the_driving_one():
    """collect_pv_data reads and assesses; collect_image_data drives the zoom.

    Recording the crosshair must never require moving the beamline, so the call
    has to be in the first of those. This asserts on the source because the
    distinction is the whole point and a future edit could quietly move it.
    """
    source = open(
        os.path.join(REPO_ROOT, "modules", "AlignBeam", "AlignBeam.py")
    ).read()
    safe = source.index("def collect_pv_data")
    driving = source.index("def collect_image_data")
    call = source.index("self.collect_crosshair_positions()")
    assert safe < call < driving, (
        "collect_crosshair_positions must be called from collect_pv_data, which "
        "moves nothing - not from collect_image_data, which drives the zoom"
    )
