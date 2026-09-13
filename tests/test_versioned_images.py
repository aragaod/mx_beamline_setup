"""Re-running a module no longer destroys the previous image (B6).

Image filenames are fixed per module - beam_at_sample.png,
rotationaxis_montage.png, robot_dewar.png - so running a module twice in a day
overwrote the first run's image with the second. The reason for re-running is
usually that something was wrong the first time, which makes the overwritten
image the one worth keeping.
"""

import logging
import os
import time

import pytest

from base.Modules import Base


@pytest.fixture
def store(tmp_path):
    class Fake:
        def __init__(self):
            self.log = logging.getLogger("versioned-image-tests")

    Fake.store_versioned = Base.__dict__["store_versioned"]
    # store_versioned delegates the archiving to displace_existing, which the
    # in-place writers (TestCrystal, SampleLoad, BeamstopAlignment) call directly.
    Fake.displace_existing = Base.__dict__["displace_existing"]
    module = Fake()
    # chown to a group the test user may not be in would fail; the real modules
    # run as staff who are.
    module.store_versioned = lambda source, destination, group=None: Base.__dict__[
        "store_versioned"
    ](module, source, destination, group=os.getgid())
    return module


def _write(path, text):
    path.write_text(text)
    return str(path)


def test_the_first_image_just_lands(store, tmp_path):
    source = _write(tmp_path / "new.png", "first")
    destination = str(tmp_path / "beam_at_sample.png")
    assert store.store_versioned(source, destination) == destination
    assert open(destination).read() == "first"


def test_the_second_run_keeps_the_first(store, tmp_path):
    destination = str(tmp_path / "beam_at_sample.png")
    store.store_versioned(_write(tmp_path / "a.png", "first"), destination)
    time.sleep(0.01)
    store.store_versioned(_write(tmp_path / "b.png", "second"), destination)

    assert open(destination).read() == "second", "the canonical name holds the newest"
    kept = [
        n
        for n in os.listdir(tmp_path)
        if n.startswith("beam_at_sample_") and n.endswith(".png")
    ]
    assert len(kept) == 1, "the displaced image must still be there"
    assert open(os.path.join(tmp_path, kept[0])).read() == "first"


def test_the_canonical_name_never_changes(store, tmp_path):
    """The report and the eLog upload both look for the fixed name, so it has to
    keep holding the latest image."""
    destination = str(tmp_path / "rotationaxis_montage.png")
    for text in ("one", "two", "three"):
        time.sleep(0.01)
        assert (
            store.store_versioned(_write(tmp_path / f"{text}.png", text), destination)
            == destination
        )
    assert open(destination).read() == "three"


def test_a_third_run_in_the_same_second_does_not_collide(store, tmp_path):
    """The archived name is built from the displaced file's timestamp, so two
    runs inside one second would otherwise produce the same name."""
    destination = str(tmp_path / "img.png")
    store.store_versioned(_write(tmp_path / "1.png", "one"), destination)
    store.store_versioned(_write(tmp_path / "2.png", "two"), destination)
    store.store_versioned(_write(tmp_path / "3.png", "three"), destination)
    archived = sorted(n for n in os.listdir(tmp_path) if n.startswith("img_"))
    assert len(archived) == 2, f"both displaced images should survive: {archived}"
    assert open(destination).read() == "three"


def test_the_archive_name_records_when_the_image_was_made(store, tmp_path):
    """Not when it was pushed aside - the name should say something true about
    the image itself."""
    destination = str(tmp_path / "img.png")
    source = _write(tmp_path / "old.png", "old")
    store.store_versioned(source, destination)
    made = time.localtime(os.path.getmtime(destination))
    time.sleep(1.1)
    store.store_versioned(_write(tmp_path / "newer.png", "new"), destination)
    archived = [n for n in os.listdir(tmp_path) if n.startswith("img_")][0]
    assert time.strftime("%H%M%S", made) in archived


def test_a_missing_source_does_not_raise(store, tmp_path):
    assert store.store_versioned("/nonexistent.png", str(tmp_path / "x.png")) is None


def test_both_modules_use_it():
    """A module copying images itself would silently keep the old behaviour."""
    import re

    from conftest import MODULES_DIR

    for module, method in (
        ("AlignBeam", "store_beam_image_for_report"),
        ("RotationAxis", "store_montage_for_report"),
    ):
        source = open(os.path.join(MODULES_DIR, module, f"{module}.py")).read()
        body = source[source.index(f"def {method}") :]
        body = body[: body.index("\n    def ")]
        assert "store_versioned" in body, f"{module}.{method} still copies directly"


# --------------------------------------------------------------------------
# The modules that build an image where it will finally live
# --------------------------------------------------------------------------


def test_displacing_works_without_a_source_file(store, tmp_path):
    """TestCrystal builds its montage directly at the final path, so there is no
    source to copy from - only an existing file to move aside.

    B6 covered only the three sites that copy into place. TestCrystal, SampleLoad
    and BeamstopAlignment all write in place and were silently still
    overwriting; a second Test Crystal run on 2026-08-31 destroyed the first
    run's montage.
    """
    destination = tmp_path / "crystalNdiff_images.png"
    _write(destination, "first run")

    archived = store.displace_existing(str(destination))

    assert archived is not None
    assert not destination.exists(), "the old image should have been moved aside"
    assert open(archived).read() == "first run"


def test_displacing_nothing_is_not_an_error(store, tmp_path):
    """The first run of the day has nothing to displace."""
    assert store.displace_existing(str(tmp_path / "not_there.png")) is None


def test_test_crystal_displaces_before_building_its_montage():
    """The call has to be on the module that builds the montage."""
    from modules.TestCrystal.TestCrystal import TestCrystal

    assert hasattr(TestCrystal, "displace_existing")
    source = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "modules",
            "TestCrystal",
            "TestCrystal.py",
        )
    ).read()
    build = source.index("def make_image_montage")
    assert "displace_existing" in source[build : build + 600]
