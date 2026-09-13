"""Recovering the four original frames from a stored rotation-axis montage.

Why this exists
---------------
`collect_four_images()` drives omega to 0, 90, 180 and 270 and captures an OAV
image at each. Those four frames are written to `/var/tmp/<user>_<angle>.jpg`,
tiled into a 2x2 montage, and only the montage is stored in the report folder.
`/var/tmp` is per-workstation and overwritten on the next run, so the originals
do not survive the morning.

That looked like it blocked B4 - a figure of merit for how well the rotation axis
is aligned needs the pin tip in each frame, and detecting a tip in an image with
synthetic straight lines drawn through it is exactly the wrong problem. It turns
out not to block anything, for three reasons found by looking at the stored
montages on 2026-08-31:

**The tiling is lossless.** Each frame occupies an exact 1024x768 rectangle at a
known offset, with a 1-pixel margin and 1-pixel padding: a 2051x1539 montage
decomposes back into four frames with no resampling.

**The drawn crosshair is a colour that cannot occur in the image.** PIL renders
`fill=128` on an RGB image as pure (128, 0, 0) - saturated dark red, and exactly
uniform. An OAV frame is greyscale. So the lines are separable to the pixel, not
merely maskable by position.

**The lines are the reference, not just contamination.** They sit at the
crosshair for the zoom in use, so every stored montage carries the crosshair as
it was *on that day*. `display.configuration` only ever holds today's, and it is
re-measured whenever the beam is realigned - the 11 August montage has its
crosshair at (468, 394) while the file now reads (464, 381). For anything
historical the montage is the better source.

So B4 can be developed against the 33 montages already stored rather than waiting
a run cycle for new data. `RotationAxis` now also keeps the four originals going
forward, which is still worth doing - it avoids this decomposition entirely and
keeps the 3 pixels the lines overwrite.

Layout
------
`make_montage()` reorders [0, 90, 180, 270] to [0, 180, 90, 270] before tiling
row-major, which puts the two pairs that get compared side by side:

    +-----------+-----------+
    |  omega 0  | omega 180 |   compared in Y
    +-----------+-----------+
    |  omega 90 | omega 270 |   compared in X
    +-----------+-----------+
"""

MARGIN = 1
PADDING = 1
FRAME_WIDTH = 1024
FRAME_HEIGHT = 768

# Row-major order after make_montage() has moved 90 behind 180.
ANGLE_ORDER = (0, 180, 90, 270)

# PIL renders ImageDraw's `fill=128` as this on an RGB image. Nothing in a
# greyscale OAV frame is saturated red, so it identifies the drawn lines exactly.
CROSSHAIR_COLOUR = (128, 0, 0)
CROSSHAIR_WIDTH = 3


def expected_size():
    """What a montage of four 1024x768 frames should measure."""
    return (
        2 * FRAME_WIDTH + 2 * MARGIN + PADDING,
        2 * FRAME_HEIGHT + 2 * MARGIN + PADDING,
    )


def frame_box(index):
    """(left, upper, right, lower) of one frame, in montage coordinates."""
    row, column = divmod(index, 2)
    left = MARGIN + column * (FRAME_WIDTH + PADDING)
    upper = MARGIN + row * (FRAME_HEIGHT + PADDING)
    return (left, upper, left + FRAME_WIDTH, upper + FRAME_HEIGHT)


def split(image):
    """{angle: PIL.Image} for the four frames.

    Raises ValueError on a montage that is not the expected shape, rather than
    returning quietly wrong crops - a frame cropped at the wrong offset still
    looks like a pin image.
    """
    if tuple(image.size) != expected_size():
        raise ValueError(
            f"Montage is {image.size}, expected {expected_size()}. "
            "It was not made by make_contact_sheet with these settings."
        )
    return {
        angle: image.crop(frame_box(index)) for index, angle in enumerate(ANGLE_ORDER)
    }


def find_crosshair(frame, tolerance=2):
    """(x, y) of the drawn crosshair in one frame, or None if it is not there.

    Found by colour rather than by position, so it does not depend on
    `display.configuration` matching what was true on the day.
    """
    import numpy as np

    pixels = np.asarray(frame.convert("RGB"), dtype=int)
    target = np.array(CROSSHAIR_COLOUR)
    drawn = np.all(np.abs(pixels - target) <= tolerance, axis=2)

    # A drawn line spans most of the frame; a stray red pixel does not.
    rows = np.where(drawn.sum(axis=1) > FRAME_WIDTH * 0.8)[0]
    columns = np.where(drawn.sum(axis=0) > FRAME_HEIGHT * 0.8)[0]
    if not len(rows) or not len(columns):
        return None
    return int(round(columns.mean())), int(round(rows.mean()))


def crosshair_mask(frame, tolerance=2):
    """Boolean array, True where the drawn crosshair covers the image.

    Three pixels of each line are not image data. Anything measuring the frame
    has to ignore them rather than treat them as a very straight edge.
    """
    import numpy as np

    pixels = np.asarray(frame.convert("RGB"), dtype=int)
    return np.all(np.abs(pixels - np.array(CROSSHAIR_COLOUR)) <= tolerance, axis=2)
