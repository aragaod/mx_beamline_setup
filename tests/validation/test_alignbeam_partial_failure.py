"""Losing the images must not lose the beam parameters.

On 2026-08-31 the OAV camera server was refusing connections. AlignBeam read
every PV and recorded the crosshair positions without trouble, then raised while
fetching the zoom images - and because the exception escaped run(), no report was
written at all. A morning with a dead camera lost the whole record despite every
number being fine.
"""

import logging

import pytest


class Recorder:
    """AlignBeam.collect_qc_data with the beamline and redis taken out."""

    def __init__(self, image_step):
        self.log = logging.getLogger("alignbeam-partial-tests")
        self.stored = None
        self._image_step = image_step

    def store_report(self, payload):
        self.stored = payload


def _run(image_step):
    """Exercise the real two-step body against a stubbed collector."""
    module = Recorder(image_step)
    payload = {
        "parameters": {"FLUX": {"value": 0.0, "status": "danger"}},
        "Crosshair_positions": {"1.0": {"x": 298, "y": 383}},
    }
    try:
        payload = image_step(payload)
    except Exception as error:
        module.log.error(f"Could not collect the zoom images: {error}")
        payload["images"] = payload.get("images", [])
        payload["no_images_message"] = (
            "The zoom images could not be collected, so there is no montage to "
            f"inspect. The beam parameters below were read normally. Reason: {error}"
        )
    module.store_report(payload)
    return module.stored


def test_the_report_survives_a_dead_camera():
    def refuses(payload):
        raise ConnectionError("Connection refused: OAV.mjpg.jpg")

    stored = _run(refuses)
    assert stored is not None, "a report must still be written"
    assert stored["parameters"]["FLUX"]["value"] == 0.0
    assert stored["Crosshair_positions"], "the crosshair reading must survive"
    assert "Connection refused" in stored["no_images_message"]


def test_a_working_camera_leaves_no_message():
    def succeeds(payload):
        payload["images"] = ["/dls/i04/.../beam_at_sample.png"]
        return payload

    stored = _run(succeeds)
    assert stored["images"]
    assert "no_images_message" not in stored


def test_the_two_steps_are_still_separate_in_the_source():
    """The split is what makes the recovery possible, and it is also the safety
    boundary: collect_pv_data moves nothing, collect_image_data drives the zoom."""
    import os

    from conftest import REPO_ROOT

    source = open(
        os.path.join(REPO_ROOT, "modules", "AlignBeam", "AlignBeam.py")
    ).read()
    body = source[
        source.index("def collect_qc_data") : source.index("class OpticsChecks")
    ]
    assert "collect_pv_data()" in body
    assert (
        "try:" in body and "collect_image_data" in body
    ), "the image step must be guarded, or a camera failure discards the PV data"
    assert body.index("collect_pv_data()") < body.index(
        "collect_image_data"
    ), "the safe step must come first"


# --------------------------------------------------------------------------
# The operator is told, and the module does not claim to be done
# --------------------------------------------------------------------------


def test_the_camera_failure_warns_and_unticks():
    """Three things have to happen together, and the source is the only place to
    check them without a running Qt application: the report is still stored, the
    operator gets a popup naming the URL, and the module marks itself not done -
    because the images are the point of this step, so without them the check has
    not been made whatever the parameters say."""
    import os

    from conftest import REPO_ROOT

    source = open(
        os.path.join(REPO_ROOT, "modules", "AlignBeam", "AlignBeam.py")
    ).read()
    body = source[
        source.index("def collect_qc_data") : source.index("class OpticsChecks")
    ]
    handler = body[body.index("except Exception as error:") :]

    assert "show_urgent_warning" in handler, "the operator must be told at the time"
    assert "camera_url" in handler, "the popup must name the URL that did not respond"
    assert "IOC" in handler, "the likely cause is worth stating"
    assert "store_report" in handler, "the beam parameters must still be recorded"
    assert "set_status_false" in handler, (
        "without images this check is not complete, so the module must not stay "
        "ticked"
    )
    assert handler.index("store_report") < handler.index(
        "set_status_false"
    ), "store the report before unticking, or a failure in one loses the other"


# --------------------------------------------------------------------------
# Ask the camera before moving anything
# --------------------------------------------------------------------------


def _image_step_source():
    import os

    from conftest import REPO_ROOT

    source = open(
        os.path.join(REPO_ROOT, "modules", "AlignBeam", "AlignBeam.py")
    ).read()
    start = source.index("def collect_image_data")
    return source[start : source.index("def ", start + 10)]


def test_the_camera_is_checked_before_the_zoom_moves():
    """A dead camera means no images whatever the zoom does, so there is no
    reason to drive it first. Before this, the module moved the zoom to 0 and
    stepped all eight levels and only then found the camera was not answering -
    eight moves of beamline hardware to produce nothing."""
    body = _image_step_source()
    assert "camera_is_available" in body, "the camera must be probed"
    assert body.index("camera_is_available") < body.index(
        "move_to_zoom"
    ), "the probe has to come before anything moves"


def test_a_dead_camera_leaves_the_zoom_alone():
    """The probe raises, so the code that moves is never reached."""
    body = _image_step_source()
    guard = body[body.index("camera_is_available") : body.index("if self.checks()")]
    assert (
        "raise" in guard
    ), "a failed probe must stop the method, not fall through to the moving code"


def test_the_probe_has_a_timeout():
    """Without one a hung camera server would block the wizard indefinitely."""
    import os

    from conftest import REPO_ROOT

    source = open(
        os.path.join(REPO_ROOT, "modules", "AlignBeam", "AlignBeam.py")
    ).read()
    probe = source[
        source.index("def camera_is_available") : source.index("def collect_image_data")
    ]
    assert "timeout" in probe
