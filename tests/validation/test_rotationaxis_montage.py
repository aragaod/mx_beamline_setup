"""Recovering the four frames from a stored rotation-axis montage (B4).

B4 - a figure of merit for how well the rotation axis is aligned - looked
blocked. The four frames it needs go to /var/tmp and are overwritten by the next
run; only the montage is kept, and the montage has a crosshair drawn through
every frame. Detecting a pin tip in an image with synthetic straight lines
through it is exactly the wrong problem to hand an edge detector.

Looking at the stored montages on 2026-08-31 showed it is not blocked. The tiling
is lossless, the drawn lines are a saturated red that cannot occur in a greyscale
OAV frame, and those lines mark the crosshair as it was on the day - which
display.configuration, holding only today's, does not.

These tests pin that decomposition, because it is the kind of thing that fails
silently: a frame cropped one pixel out still looks like a pin image.
"""

import glob
import os

import pytest

pytest.importorskip("PIL")

from PIL import Image, ImageDraw  # noqa: E402

from modules.RotationAxis.montage import (  # noqa: E402
    ANGLE_ORDER,
    CROSSHAIR_COLOUR,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    crosshair_mask,
    expected_size,
    find_crosshair,
    frame_box,
    split,
)

REAL_MONTAGES = sorted(
    glob.glob(
        "/dls/i04/data/2026/*/beamline_setup/*/RotationAxis/rotationaxis_montage.png"
    )
)


def build_montage(crosshair=(464, 381), marks=None):
    """A montage made exactly the way make_contact_sheet makes one.

    Each frame is given a distinct grey so the crops can be told apart, plus an
    optional bright mark to stand in for a pin tip.
    """
    montage = Image.new("RGB", expected_size(), (255, 255, 255))
    for index, angle in enumerate(ANGLE_ORDER):
        shade = 40 + index * 30
        frame = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), (shade, shade, shade))
        if marks and angle in marks:
            x, y = marks[angle]
            ImageDraw.Draw(frame).ellipse(
                (x - 6, y - 6, x + 6, y + 6), fill=(250, 250, 250)
            )
        draw = ImageDraw.Draw(frame)
        draw.line((0, crosshair[1], FRAME_WIDTH, crosshair[1]), fill=128, width=3)
        draw.line((crosshair[0], 0, crosshair[0], FRAME_HEIGHT), fill=128, width=3)
        montage.paste(frame, frame_box(index)[:2])
    return montage


# --------------------------------------------------------------------------
# The geometry
# --------------------------------------------------------------------------


def test_the_montage_is_the_size_the_tiling_implies():
    """2 x 1024 + 2 margins + 1 padding, and the same vertically."""
    assert expected_size() == (2051, 1539)


def test_the_four_frames_come_back_keyed_by_angle():
    frames = split(build_montage())
    assert sorted(frames) == [0, 90, 180, 270]
    assert all(f.size == (FRAME_WIDTH, FRAME_HEIGHT) for f in frames.values())


def test_the_pairs_that_get_compared_are_where_the_layout_says():
    """make_montage moves 90 behind 180 so the two compared pairs sit side by
    side: 0 and 180 across the top, 90 and 270 across the bottom."""
    assert ANGLE_ORDER == (0, 180, 90, 270)
    assert frame_box(0)[1] == frame_box(1)[1]  # 0 and 180 share a row
    assert frame_box(2)[1] == frame_box(3)[1]  # 90 and 270 share a row


def test_each_frame_is_the_one_it_claims_to_be():
    """A crop taken at the wrong offset still looks like a pin image, so this
    checks identity rather than plausibility."""
    frames = split(build_montage())
    shades = {angle: frames[angle].getpixel((10, 10))[0] for angle in ANGLE_ORDER}
    assert shades == {0: 40, 180: 70, 90: 100, 270: 130}


def test_a_montage_of_the_wrong_shape_is_refused():
    """Returning quietly wrong crops would be worse than failing."""
    with pytest.raises(ValueError):
        split(Image.new("RGB", (800, 600)))


# --------------------------------------------------------------------------
# The drawn crosshair
# --------------------------------------------------------------------------


def test_the_crosshair_is_found_by_colour_not_by_position():
    """So it does not depend on display.configuration matching the day."""
    frames = split(build_montage(crosshair=(500, 300)))
    assert find_crosshair(frames[0]) == (500, 300)


def test_every_frame_agrees_on_the_crosshair():
    frames = split(build_montage(crosshair=(470, 390)))
    assert len({find_crosshair(f) for f in frames.values()}) == 1


def test_a_frame_with_no_crosshair_says_so_rather_than_guessing():
    plain = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), (60, 60, 60))
    assert find_crosshair(plain) is None


def test_a_stray_red_pixel_is_not_a_crosshair():
    """A line spans the frame; a speck does not."""
    plain = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), (60, 60, 60))
    ImageDraw.Draw(plain).point((100, 100), fill=CROSSHAIR_COLOUR)
    assert find_crosshair(plain) is None


def test_the_drawn_lines_are_maskable_to_the_pixel():
    """Three pixels of each line are not image data. Anything measuring the
    frame has to ignore them rather than read them as a very straight edge."""
    frames = split(build_montage(crosshair=(500, 300)))
    mask = crosshair_mask(frames[0])
    assert mask[299:302, :].all()
    assert mask[:, 499:502].all()
    assert not mask[100, 100]


def test_the_crosshair_colour_cannot_occur_in_a_greyscale_frame():
    """PIL renders fill=128 as this on RGB. An OAV frame is grey, so red and
    blue can never differ this much - which is what makes the lines separable."""
    red, green, blue = CROSSHAIR_COLOUR
    assert red != green and green == blue


# --------------------------------------------------------------------------
# Against what is actually stored
# --------------------------------------------------------------------------


@pytest.mark.skipif(not REAL_MONTAGES, reason="no stored montages on this machine")
def test_every_stored_montage_decomposes():
    """33 of 33 did when this was written. A montage that does not is a change
    in how the contact sheet is built, and B4 would silently measure nonsense."""
    failures = []
    for path in REAL_MONTAGES:
        try:
            frames = split(Image.open(path))
        except ValueError as error:
            failures.append((path, str(error)))
            continue
        if any(find_crosshair(frame) is None for frame in frames.values()):
            failures.append((path, "no crosshair found"))
    assert not failures, failures[:3]


@pytest.mark.skipif(not REAL_MONTAGES, reason="no stored montages on this machine")
def test_a_stored_montage_carries_the_crosshair_of_its_own_day():
    """display.configuration holds only today's, and it is re-measured whenever
    the beam is realigned. Over 33 days the drawn crosshair moved about 8 px in
    X and 12 in Y, so a historical frame must take its reference from itself."""
    found = set()
    for path in REAL_MONTAGES[:12]:
        frames = split(Image.open(path))
        found.add(find_crosshair(frames[0]))
    assert len(found) > 1, "the crosshair should differ between days"


# --------------------------------------------------------------------------
# Finding the pin tip, and the eccentricity (B4)
# --------------------------------------------------------------------------

from modules.RotationAxis.eccentricity import (  # noqa: E402
    TipNotFound,
    eccentricity,
    find_tip,
    measure,
    otsu_threshold,
)

import numpy as np  # noqa: E402


def pin_frame(tip_x=470, tip_y=384, background=103, needle=30, specks=True):
    """A frame shaped like the real ones: a dark wedge entering from the right,
    tip pointing left, on flat grey, with dust.

    The background level matters. It is about 103 in the real frames, not the
    150 it looks like on screen, and the white angle label pushes the maximum to
    255 - which is what broke a threshold set as a fraction of (min, max).
    """
    frame = Image.new("L", (FRAME_WIDTH, FRAME_HEIGHT), background)
    draw = ImageDraw.Draw(frame)
    draw.polygon(
        [(tip_x, tip_y), (FRAME_WIDTH, tip_y - 60), (FRAME_WIDTH, tip_y + 60)],
        fill=needle,
    )
    draw.text((10, 10), "0", fill=255)
    if specks:
        # Dust. Taking the extreme dark pixel finds one of these instead of the
        # tip, which produced an eccentricity of exactly 0.00 on all 33 days.
        for x, y in ((60, 200), (150, 500), (900, 700), (30, 400)):
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=needle)
    return frame.convert("RGB")


def test_the_tip_is_found_where_it_was_drawn():
    x, y = find_tip(pin_frame(tip_x=470, tip_y=384))
    assert abs(x - 470) <= 2
    assert abs(y - 384) <= 2


def test_dust_does_not_become_the_tip():
    """The specks are further left than the tip and just as dark."""
    x, _ = find_tip(pin_frame(tip_x=470, specks=True))
    assert x > 400, "a speck at x=30 was taken for the pin tip"


def test_a_frame_with_no_pin_is_refused():
    """An eccentricity from a speck of dirt looks exactly like a measurement."""
    blank = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), (103, 103, 103))
    ImageDraw.Draw(blank).ellipse((100, 100, 110, 110), fill=(30, 30, 30))
    with pytest.raises(TipNotFound):
        find_tip(blank)


def test_the_threshold_survives_a_bright_label():
    """Otsu splits the two modes; a fraction of the grey range does not, because
    the white text puts the maximum at 255 and the split lands above the
    background - which called the whole frame dark."""
    frame = pin_frame()
    grey = np.asarray(frame.convert("L"), dtype=float)
    threshold = otsu_threshold(grey)
    assert 30 <= threshold < 103


def test_a_failed_threshold_is_refused_rather_than_measured():
    """A pin covering most of the frame is a threshold that did not separate."""
    dark = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), (30, 30, 30))
    ImageDraw.Draw(dark).rectangle(
        (0, 0, FRAME_WIDTH, FRAME_HEIGHT - 5), fill=(28, 28, 28)
    )
    with pytest.raises(TipNotFound):
        find_tip(dark)


def test_an_equal_and_opposite_pair_is_perfectly_centred():
    """The whole point of the measurement. A tip 3 px above the crosshair at 0
    and 3 px below at 180 sits exactly on the rotation axis - it is the
    crosshair that is elsewhere, and measuring against it would call this
    misaligned."""
    figures = eccentricity({0: (470, 381.0), 180: (470, 387.0)})
    assert figures["eccentricity_0_180_px"] == pytest.approx(3.0)
    assert figures["axis_y_0_180_px"] == pytest.approx(384.0)


def test_a_tip_on_the_axis_gives_zero():
    figures = eccentricity({0: (470, 384.0), 180: (470, 384.0)})
    assert figures["eccentricity_0_180_px"] == 0.0


def test_the_two_pairs_combine_as_orthogonal_components():
    figures = eccentricity(
        {0: (470, 381.0), 180: (470, 387.0), 90: (470, 380.0), 270: (470, 388.0)}
    )
    assert figures["eccentricity_px"] == pytest.approx(5.0)  # 3-4-5


def test_a_missing_frame_leaves_its_pair_out_rather_than_guessing():
    figures = eccentricity({0: (470, 381.0), 90: (470, 380.0), 270: (470, 388.0)})
    assert "eccentricity_0_180_px" not in figures
    assert "eccentricity_90_270_px" in figures
    assert "eccentricity_px" not in figures


def test_measure_names_the_frames_it_could_not_read():
    blank = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), (103, 103, 103))
    _, _, missing = measure({0: pin_frame(), 180: blank})
    assert [angle for angle, _ in missing] == [180]


@pytest.mark.skipif(not REAL_MONTAGES, reason="no stored montages on this machine")
def test_a_montage_will_not_be_measured_through_its_own_crosshair():
    """The correction that matters.

    The crosshair is drawn at the crosshair position, which on a well-aligned
    beamline is exactly where the tip is - 0 to 1 px away on 7 August 2026,
    against a line 3 px wide. Masking it removes the feature being measured, and
    the same morning came out at 0.79 px from the original frames and 3.72 px
    from the montage crops.

    So passing the crosshair to measure() must make it refuse rather than return
    the inflated number.
    """
    from modules.RotationAxis.eccentricity import TipUnderCrosshair

    refused = 0
    for path in REAL_MONTAGES[-12:]:
        frames = split(Image.open(path))
        crosshair = find_crosshair(frames[0])
        masks = {angle: crosshair_mask(f) for angle, f in frames.items()}
        _, _, missing = measure(frames, masks, crosshair=crosshair)
        if any("crosshair" in why for _, why in missing):
            refused += 1
    assert refused, (
        "no montage was refused, so the crosshair conflict is not being caught "
        "and montage-derived eccentricities are being trusted"
    )


def test_measuring_without_a_crosshair_argument_still_works():
    """The original frames have no drawn crosshair, and that is the path that
    matters from here on - the module now keeps them."""
    frames = {0: pin_frame(tip_y=381), 180: pin_frame(tip_y=387)}
    tips, figures, missing = measure(frames)
    assert not missing
    assert figures["eccentricity_0_180_px"] == pytest.approx(3.0, abs=0.5)


def test_a_tip_clear_of_the_crosshair_is_still_measured():
    """The refusal must be about the tip being covered, not about montages."""
    frames = {0: pin_frame(tip_y=300), 180: pin_frame(tip_y=306)}
    _, figures, missing = measure(frames, crosshair=(470, 384))
    assert not missing
    assert "eccentricity_0_180_px" in figures


# --------------------------------------------------------------------------
# Sub-pixel y from the needle's centreline (B9)
# --------------------------------------------------------------------------

from modules.RotationAxis.eccentricity import find_centreline  # noqa: E402


def wedge_frame(tip_x=470, tip_y=384, slope=0.0, half_angle=0.11):
    """A clean wedge with a known centreline, so the answer is known exactly.

    `slope` tilts the centreline; `half_angle` sets how fast the wedge opens.
    """
    frame = Image.new("L", (FRAME_WIDTH, FRAME_HEIGHT), 103)
    draw = ImageDraw.Draw(frame)
    far = FRAME_WIDTH
    reach = far - tip_x
    draw.polygon(
        [
            (tip_x, tip_y),
            (far, tip_y + slope * reach - half_angle * reach),
            (far, tip_y + slope * reach + half_angle * reach),
        ],
        fill=30,
    )
    draw.text((10, 10), "0", fill=255)
    return frame.convert("RGB")


def test_the_centreline_is_sub_pixel_not_an_integer():
    """The whole point of B9: the y must not be quantised to whole pixels."""
    x, y = find_centreline(wedge_frame(tip_y=384, slope=0.013))
    assert isinstance(y, float)
    assert y != round(y), "the centreline came back on a pixel boundary"


def test_the_centreline_recovers_a_known_geometry():
    """A flat wedge's centreline is its tip height, wherever it is read."""
    _, y = find_centreline(wedge_frame(tip_y=390, slope=0.0), offset=40)
    assert abs(y - 390) < 0.5


def test_the_centreline_follows_a_tilted_needle():
    """Read 40 columns back from a needle sloping 0.02 px per column, the
    centreline should sit about 0.8 px below the tip."""
    _, y = find_centreline(wedge_frame(tip_y=380, slope=0.02), offset=40)
    assert abs(y - (380 + 0.02 * 40)) < 0.6


def test_the_centreline_is_far_more_repeatable_than_the_apex():
    """Measured on the real frames: about 0.02 px of standard error against
    about 2 px. Here, the same wedge photographed at two tip positions one pixel
    apart should shift the centreline by very close to one pixel, whereas the
    apex quantises."""
    _, low = find_centreline(wedge_frame(tip_y=384, slope=0.01))
    _, high = find_centreline(wedge_frame(tip_y=385, slope=0.01))
    assert abs((high - low) - 1.0) < 0.25


def test_a_frame_with_too_little_needle_is_refused():
    """Fewer than 30 usable columns is not enough to fit a line through."""
    frame = Image.new("L", (FRAME_WIDTH, FRAME_HEIGHT), 103)
    ImageDraw.Draw(frame).polygon(
        [(1015, 384), (FRAME_WIDTH, 370), (FRAME_WIDTH, 398)], fill=30
    )
    with pytest.raises(TipNotFound):
        find_centreline(frame.convert("RGB"))


def test_measure_takes_its_y_from_the_centreline_and_its_refusals_from_the_apex():
    """Both estimators have a job: the apex decides whether there is a pin at
    all, the centreline supplies the number."""
    frames = {
        0: wedge_frame(tip_y=381, slope=0.01),
        180: wedge_frame(tip_y=387, slope=0.01),
    }
    tips, figures, missing = measure(frames)
    assert not missing
    # The y must be the sub-pixel one, not the apex's whole-pixel row average.
    assert tips[0][1] != round(tips[0][1]) or tips[180][1] != round(tips[180][1])
    assert abs(figures["eccentricity_0_180_px"] - 3.0) < 0.4

    # ...and a frame with no pin is still refused, by the apex detector.
    blank = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), (103, 103, 103))
    _, _, missing = measure({0: wedge_frame(), 180: blank})
    assert [angle for angle, _ in missing] == [180]
