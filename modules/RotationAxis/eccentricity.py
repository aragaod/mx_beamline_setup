"""How far the pin tip sits from the rotation axis, in pixels (B4).

The module already drives omega to 0, 90, 180 and 270 and photographs the pin at
each, but produced no number for how well the axis is actually aligned - the four
images went into a montage for a person to look at.

The measurement
---------------
Rotating omega by 180 degrees moves an off-axis point to the opposite side of the
axis. So if the tip is `d` above the axis at omega 0, it is `d` below at 180, and
the axis itself is the **midpoint** of the two tip positions:

    eccentricity = |y(0) - y(180)| / 2

The important subtlety is that this is not the distance from the crosshair. A
tip 3 px above the crosshair at 0 and 3 px below at 180 is perfectly centred on
the rotation axis; it is the crosshair that sits elsewhere. Measuring against the
crosshair would call that misaligned, which is why the figure of merit is the
difference between the pair rather than either one's offset.

The 90/270 pair gives the same measurement for the component that was pointing
along the viewing direction at 0/180, so between them the two pairs cover both
axes perpendicular to omega. Both are reported.

A montage is not good enough to measure from
--------------------------------------------
`montage.py` recovers the four frames from a stored montage exactly, and the
drawn lines are separable to the pixel. That is true and still useful - but it
does **not** mean a montage can be measured.

The crosshair is drawn at the crosshair position, and on a well-aligned beamline
that is precisely where the tip is. On 7 August 2026 the tip sat 0 to 1 px from
the drawn horizontal line, which is 3 px wide: the line covers the tip
completely. Masking it and filling with background removes the feature being
measured, and the detector then finds the edge of whichever fragment survives.

Same morning, measured both ways:

    from the original frames    0.79 px
    from the montage crops      3.72 px

So the montage number is mostly artefact. Historical montages give an upper
bound and nothing better; a real measurement needs the frames as captured, which
the module now keeps.

Finding the needle
------------------
Easier than it sounds, because of what the images actually look like: a
near-black needle on a flat grey background, entering from one side, roughly
horizontal. No edge detection and no OpenCV - the pin is 70 grey levels darker
than everything around it, so an Otsu threshold and the largest connected dark
region give the silhouette, and that is easy to debug at 2 a.m.

The drawn crosshair has to be masked first. It is 3 pixels wide and would
otherwise be the straightest edge in the frame.

Where the y comes from, and why not the apex (B9)
-------------------------------------------------
`find_tip` returns the silhouette's apex. It is what refuses a frame holding no
pin, the scintillator, or only dust, and its x is used as the reference point.
Its **y is not used for the measurement**, because it comes from a handful of
pixels at the tip and carries about 2 px of noise - the same size as the
eccentricity being measured. A number whose error matches its signal cannot
drive an alignment routine.

`find_centreline` supplies the y instead: the average of the needle's two edges,
fitted over 200 columns and read at a fixed offset back from the apex. Measured
on the surviving original frames, the fit residual is 0.25-0.40 px per column,
so the standard error on the fitted y is about **0.02 px** - roughly fifty times
better, and comfortably sub-pixel.

**A route that was tried and is worse**: fitting both edges and intersecting them
to find the apex. A thin wedge's edges are nearly parallel, so the intersection
is hypersensitive to slope error - on the same frames it gave 9.7 px of noise
against 2.0 for simply taking the extreme pixel. The eccentricity never needed
the apex; it needs a y that is comparable between omega 0 and 180, and the
centreline is that without extrapolating anywhere.
"""

import numpy as np

# How much of the frame the pin may occupy. A "pin" covering most of the image is
# a failed threshold, not a pin - which is what a fixed fraction of the grey
# range produced before this used Otsu: the white angle label pushes the maximum
# to 255, so a fraction of (min, max) landed above the background and called the
# whole frame dark.
MAXIMUM_PIN_FRACTION = 0.35

# Below this the "needle" is a speck of dirt or a shadow, not a pin.
MINIMUM_PIN_PIXELS = 2000


# The drawn crosshair is 3 px wide and, on a well-aligned beamline, sits exactly
# where the tip is. A tip found this close to it has been measured through a hole
# in the image.
CROSSHAIR_CONFLICT_PX = 6


class TipNotFound(Exception):
    """No pin in the frame, or nothing that looks like one."""


class TipUnderCrosshair(TipNotFound):
    """The tip sits under the drawn crosshair, so the frame cannot give it.

    Not a detection failure - the opposite. It means the axis is well aligned,
    because the tip is where the crosshair is. It just cannot be measured from a
    montage; it needs the original frame.
    """


def otsu_threshold(pixels):
    """The grey level that best separates the pin from the background.

    Otsu's method: pick the threshold that minimises the variance within the two
    groups it creates. Used rather than a fixed constant because the histogram is
    strongly bimodal - the needle sits around 30 and the background around 103 -
    and the separation is obvious, but where it sits in absolute terms is not
    stable between frames.
    """
    counts, edges = np.histogram(pixels, bins=256, range=(0, 256))
    total = counts.sum()
    if not total:
        raise TipNotFound("empty frame")
    levels = np.arange(256)
    weight_below = np.cumsum(counts)
    weight_above = total - weight_below
    usable = (weight_below > 0) & (weight_above > 0)
    if not usable.any():
        raise TipNotFound("frame is a single grey level")

    sum_below = np.cumsum(counts * levels)
    sum_total = sum_below[-1]
    mean_below = np.divide(
        sum_below, weight_below, out=np.zeros(256), where=weight_below > 0
    )
    mean_above = np.divide(
        sum_total - sum_below, weight_above, out=np.zeros(256), where=weight_above > 0
    )
    between = weight_below * weight_above * (mean_below - mean_above) ** 2
    between[~usable] = -1
    return float(np.argmax(between))


def _greyscale(frame, mask=None):
    pixels = np.asarray(frame.convert("L"), dtype=float)
    if mask is not None:
        # The drawn lines are not image data. Filling them with the background
        # keeps them from being either a pin or a hole in one.
        pixels = pixels.copy()
        pixels[mask] = np.median(pixels[~mask])
    return pixels


def find_tip(frame, mask=None):
    """(x, y) of the pin tip, in frame pixels.

    Raises TipNotFound rather than returning a plausible wrong point: an
    eccentricity computed from a speck of dirt is worse than no number, because
    it looks like a measurement.

    The dust is why this takes the largest connected dark region rather than the
    extreme dark pixel. The frames have a dozen or so dark specks scattered
    across the background, and taking the leftmost dark pixel finds one of those
    every time - which produced an eccentricity of exactly 0.00 on all 33 days,
    the same wrong answer so consistently that it looked like a result.
    """
    from scipy import ndimage

    pixels = _greyscale(frame, mask)
    dark = pixels <= otsu_threshold(pixels)
    if dark.mean() > MAXIMUM_PIN_FRACTION:
        # Almost always this means there is no pin in the frame: with nothing
        # dark to find, Otsu splits the background's own gradient down the
        # middle and about half the frame comes back "dark". Four mornings in
        # early 2026 look like this - the pin sat outside the field of view -
        # and one had the scintillator in instead of a pin.
        raise TipNotFound(
            f"{dark.mean():.0%} of the frame is below the threshold, which means "
            "there is nothing dark enough here to be a pin"
        )

    labels, count = ndimage.label(dark)
    if not count:
        raise TipNotFound("nothing dark in this frame")
    sizes = ndimage.sum(dark, labels, range(1, count + 1))
    pin = dark & (labels == int(np.argmax(sizes)) + 1)
    if pin.sum() < MINIMUM_PIN_PIXELS:
        raise TipNotFound(
            f"largest dark region is {int(pin.sum())} pixels, too small for a pin"
        )

    # The pin runs off one side of the frame. Which side tells us which end is
    # the tip: the free end is the one furthest from where it enters.
    height, width = pin.shape
    touches_left = pin[:, 0].any()
    touches_right = pin[:, -1].any()
    if not (touches_left or touches_right):
        raise TipNotFound("the pin does not reach either edge of the frame")
    if touches_left and touches_right:
        raise TipNotFound("the dark region spans the frame; this is not a pin")
    enters_on_right = touches_right

    columns = np.where(pin.any(axis=0))[0]
    tip_x = int(columns.min() if enters_on_right else columns.max())

    # Average the dark rows over a few columns at the tip: one column alone is
    # noisy, and the tip is a wedge rather than a point.
    window = (
        pin[:, tip_x : tip_x + 5]
        if enters_on_right
        else pin[:, max(0, tip_x - 4) : tip_x + 1]
    )
    rows = np.where(window.any(axis=1))[0]
    if not len(rows):
        raise TipNotFound("no dark rows at the tip")
    return tip_x, float(rows.mean())


def needle_mask(frame, mask=None):
    """The largest connected dark region: the needle, without the dust.

    Split out of `find_tip` so both estimators work from exactly the same
    silhouette and any difference between them is the estimator, not the
    threshold.
    """
    from scipy import ndimage

    pixels = _greyscale(frame, mask)
    dark = pixels <= otsu_threshold(pixels)
    if dark.mean() > MAXIMUM_PIN_FRACTION:
        raise TipNotFound(
            f"{dark.mean():.0%} of the frame is below the threshold, which means "
            "there is nothing dark enough here to be a pin"
        )
    labels, count = ndimage.label(dark)
    if not count:
        raise TipNotFound("nothing dark in this frame")
    sizes = ndimage.sum(dark, labels, range(1, count + 1))
    pin = dark & (labels == int(np.argmax(sizes)) + 1)
    if pin.sum() < MINIMUM_PIN_PIXELS:
        raise TipNotFound(
            f"largest dark region is {int(pin.sum())} pixels, too small for a pin"
        )
    return pin


def find_centreline(frame, mask=None, offset=40, span=200, margin=12):
    """(x, y) on the needle's centreline, a fixed distance back from the tip.

    **Not the apex.** Fitting the two edges and intersecting them to find the
    apex was tried first and is much worse: a thin wedge's edges are nearly
    parallel, so the intersection is hypersensitive to slope error. Measured on
    the same frames, that gave 9.7 px of noise against 2.0 px for simply taking
    the extreme dark pixel.

    The eccentricity does not need the apex. It needs a **y** that can be
    compared between omega 0 and omega 180, and any repeatable reference on the
    needle will do. The centreline is the average of the two edges, so it uses
    every column in the fitted range and the errors on the two edges partly
    cancel - and reading it at a fixed offset back from the tip avoids
    extrapolating anywhere.

    `offset` is how far back along the needle to report, `span` how many columns
    are fitted, `margin` how many nearest the apex to skip, where the wedge is
    only a few pixels tall.
    """
    pin = needle_mask(frame, mask)
    height, width = pin.shape

    touches_left, touches_right = pin[:, 0].any(), pin[:, -1].any()
    if not (touches_left or touches_right):
        raise TipNotFound("the pin does not reach either edge of the frame")
    if touches_left and touches_right:
        raise TipNotFound("the dark region spans the frame; this is not a pin")
    enters_on_right = touches_right

    columns = np.where(pin.any(axis=0))[0]
    apex = int(columns.min() if enters_on_right else columns.max())
    step = 1 if enters_on_right else -1

    centres, used = [], []
    for index in range(margin, margin + span):
        column = apex + step * index
        if not (0 <= column < width):
            continue
        rows = np.where(pin[:, column])[0]
        # A split column - the needle plus a speck above it - would drag the
        # centre, so require the dark run to be contiguous.
        if len(rows) < 3 or rows[-1] - rows[0] + 1 != len(rows):
            continue
        centres.append((rows[0] + rows[-1]) / 2.0)
        used.append(float(index))

    if len(used) < 30:
        raise TipNotFound(
            f"only {len(used)} usable columns along the needle; too few to fit "
            "its centreline"
        )

    slope, intercept = np.polyfit(np.asarray(used), np.asarray(centres), 1)
    y = slope * offset + intercept
    if not (0 <= y < height):
        raise TipNotFound(f"fitted centreline at y={y:.1f} is outside the frame")
    return float(apex + step * offset), float(y)


def eccentricity(tips):
    """Figures of merit from {angle: (x, y)}.

    Returns a dictionary of what could be measured. A pair that is missing a
    frame is simply absent rather than guessed at.
    """
    out = {}
    for label, (first, second) in (
        ("0_180", (0, 180)),
        ("90_270", (90, 270)),
    ):
        if first not in tips or second not in tips:
            continue
        out[f"eccentricity_{label}_px"] = abs(tips[first][1] - tips[second][1]) / 2
        # Where the axis actually is, which is the useful thing to compare
        # against the crosshair separately.
        out[f"axis_y_{label}_px"] = (tips[first][1] + tips[second][1]) / 2

    both = [
        out.get("eccentricity_0_180_px"),
        out.get("eccentricity_90_270_px"),
    ]
    if all(value is not None for value in both):
        # The two pairs measure orthogonal components of the same offset.
        out["eccentricity_px"] = float(np.hypot(*both))
    return out


def measure(frames, masks=None, crosshair=None):
    """Tips and eccentricity for {angle: PIL.Image}.

    Returns (tips, figures, missing). Frames where no tip could be found are
    named rather than dropped silently.

    Pass `crosshair` when the frames came out of a montage. The lines are drawn
    at the crosshair, which on a well-aligned beamline is exactly where the tip
    is, so masking them removes the feature being measured - see the warning at
    the top of this module. Measured on 7 August 2026 against the original
    frames of the same morning: 0.79 px from the originals, 3.72 px from the
    montage crops. Refusing is the only honest option.
    """
    tips, missing = {}, []
    for angle, frame in frames.items():
        frame_mask = None if masks is None else masks.get(angle)
        try:
            # `find_tip` locates the silhouette's apex, and it is what refuses a
            # frame holding no pin, the scintillator, or only dust. Its y comes
            # from a handful of pixels at the tip, so it carries about 2 px of
            # noise - the same size as the thing being measured.
            apex = find_tip(frame, frame_mask)
            if (
                crosshair is not None
                and abs(apex[1] - crosshair[1]) <= CROSSHAIR_CONFLICT_PX
            ):
                raise TipUnderCrosshair(
                    f"tip is {abs(apex[1] - crosshair[1]):.1f} px from the drawn "
                    "crosshair, which covers it - measure the original frame"
                )
            # The measurement itself takes its y from the centreline: same
            # silhouette, hundreds of columns, a standard error of about 0.02 px
            # rather than 2. See B9 in PROGRESS.md.
            _, y = find_centreline(frame, frame_mask)
            tips[angle] = (apex[0], y)
        except TipNotFound as error:
            missing.append((angle, str(error)))
    return tips, eccentricity(tips), missing
