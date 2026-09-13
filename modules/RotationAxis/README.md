# RotationAxis

Checks the goniometer and smargon stub positions against yesterday, and captures
pin images at four omega angles.

## Files

| File | What it does |
|---|---|
| `RotationAxis.py` | `RotationAxis` assesses; `DriveBeamline` collects images. |
| `GUI_RotationAxis.py` | Two wizard pages. |
| `RotationAxis.yaml` | Wizard text. |
| `montage.py` | Recovers the four original frames from a stored montage. |
| `eccentricity.py` | Finds the pin tip and measures the rotation axis. |
| `RotationAxis.i04.yaml` | i04's PVs, thresholds, smargon home check. |
| `CaptureImages.py` | Not imported by anything. An earlier attempt at showing EPICS images in Qt. |

## This module turns the goniometer

That is what it is for: `collect_CoR_data()` calls `cameras.zoom.set(7.5)` and
`motors.omega.move(angle, wait=True, ignore_limits=True)` to photograph the pin at
four angles. The first wizard page tells the operator to make sure it is safe to
rotate before pressing Next, which is where that judgement belongs.

Two things worth knowing when editing it:

- **Neither call is a `caput`.** They go through `beamline` library device objects
  and read as ordinary attribute access, so grepping for `caput` will not find
  them.
- **`ignore_limits=True` is correct here, not a risk.** A rotating goniometer
  turns continuously: omega has no meaningful low and high limit to respect, only
  a controller count that eventually wraps. There is no safety net being bypassed,
  because there is none to bypass on this axis.

## What it reports

- **`STUB_X/Y/Z`, `GONP_Y/Z`** — change since yesterday, at the 0.001 level.
  This is why the PVs are read raw rather than through their display precision.
- **`GONP_X`** — must sit near zero, checked as a range rather than a change.
- **`Smargon_home`** — `HOMESTATUS_MSG` holds a formatted timestamp, not free
  text, so `time_since` parses it. The popup during the wizard reads its threshold
  from this same rule, so the two cannot disagree; they did until 2026-08-31, when
  the popup said 6 hours and the report said 8.

## The figure of merit (B4)

For years this module drove omega to four angles, photographed the pin at each,
and produced no number from them - the four images went into a montage for a
person to look at.

`Rotation_axis_eccentricity_px` is that number. Rotating omega by 180 degrees
puts an off-axis point on the other side of the axis, so the axis is the
**midpoint** of the two tip positions and the eccentricity is half their
separation:

    eccentricity = |y(0) - y(180)| / 2

**It is not the distance from the crosshair.** A tip 3 px above the crosshair at
omega 0 and 3 px below at 180 sits exactly on the rotation axis; it is the
crosshair that is elsewhere. Measuring against the crosshair would call that
misaligned, which is the mistake this measurement exists to avoid.

The 90/270 pair measures the component that was pointing along the viewing
direction at 0/180, so between them the two pairs cover both axes perpendicular
to omega.

### Finding the tip

Deliberately not OpenCV. The frames are a near-black needle on a flat grey
background: an Otsu threshold and the extreme point of the largest dark region
is sufficient, and it is easier to debug at 2 a.m. than an edge detector.

Two things had to be got right, and both produced convincing wrong answers first:

  * **Dust.** The background carries a dozen or so dark specks. Taking the
    leftmost dark pixel finds one of them rather than the tip, which gave an
    eccentricity of exactly 0.00 on every day - the same wrong answer so
    consistently that it looked like a result. Hence the largest *connected*
    region.
  * **The threshold.** The needle sits around grey 30 and the background around
    103, but the white angle label pushes the maximum to 255, so a threshold set
    as a fraction of the grey range lands above the background and calls the
    whole frame dark. Otsu splits the two modes wherever they happen to be.

### A montage cannot be measured, only the originals

The stored montages decompose exactly and the drawn lines are separable to the
pixel - but that does not make a montage measurable, and assuming it did produced
a number that looked entirely reasonable and was mostly artefact.

The crosshair is drawn **at the crosshair**, and on a well-aligned beamline that
is exactly where the tip is. On 7 August 2026 the tip sat 0 to 1 px from the
drawn horizontal line, which is 3 px wide - the line covers it. Masking the line
and filling with background removes the feature being measured, and the detector
then finds the edge of whichever fragment survives.

Both ways, same morning:

| measured from | eccentricity |
|---|---|
| the original frames, off `/var/tmp` | **0.79 px** |
| the montage crops | 3.72 px |

So `measure()` refuses when a tip is within 6 px of a drawn crosshair. Historical
montages give an upper bound and nothing better. This is why the module now keeps
the originals - not a nicety, a requirement.

### How good is it

Honest answer: **coarse**. The detector's own noise, measured from the spread in
x across the four angles (rotation about x cannot move the tip in x, so any
spread there is noise), is about **2 px** on original frames and 3 px on montage
crops. The eccentricity being measured is of the same order. Treat it as an
indicator, not a precise number, and do not read the decimals.

The shipped limits rest on **five measurements** - one run each from five staff,
the only original frames that survived - which gave 0.79, 0.79, 1.77, 1.82 and
2.26 px. They should be re-derived once a few weeks of runs have stored their
own originals.

`dev/review_tip_detection.py` draws the detected tip onto the image with a
magnified inset, so what the detector is doing can be judged rather than assumed.
That is how both mistakes above were found.

### Where the images come from

The four frames were written to `/var/tmp/<user>_<angle>.jpg`, which is
per-workstation and overwritten by the next run, so only the montage survived the
morning - and the montage has a crosshair drawn through every frame.

That turned out not to block anything. `montage.py` decomposes a stored montage
losslessly: the tiling is exact, and the drawn lines are a saturated red that
cannot occur in a greyscale frame. They are also the reference - each montage
carries the crosshair **as it was on that day**, which `display.configuration`,
holding only today's, does not. Over one visit the crosshair moved about 8 px in
X and 12 in Y.

The module now also keeps the four originals beside the montage, which avoids the
decomposition and keeps the three pixels per line the crosshair overwrites.

## Porting to another beamline

**i04-1 has a goniometer, not a smargon**, so it has no homing check and no stub
offsets. It does not need a mapping layer — its override sets
`smargon_home_age_check: null` and nulls the `STUB_*` rules, and they disappear.
The zoom used for the images is 7.5x on i04, which i04-1 does not have.

## Open work

**B4**, a figure of merit for how well the rotation axis is actually aligned, is
specified in `PROGRESS.md` but not built. Two things to settle first: whether the
stored images are the montage with the crosshair lines already drawn on — which
would defeat an edge detector — and locating the i03 bluesky/Artemis OpenCV
loop-centring code to adapt rather than starting fresh.
