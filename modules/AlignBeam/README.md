# AlignBeam

Checks that the beam is where it should be and delivering what it should, after
the staff member has aligned the crosshair. It is the module with the most
numbers in it, and the only one besides RotationAxis that drives anything.

## Files

| File | What it does |
|---|---|
| `AlignBeam.py` | `AlignBeam` orchestrates; `OpticsChecks` does the work; `BeamlineEpics` is the PV device wrapper. |
| `GUI_AlignBeam.py` | Two wizard pages. |
| `AlignBeam.yaml` | Wizard text, `hidden_parameters`. |
| `AlignBeam.i04.yaml` | i04's PVs, thresholds and zoom PV. |

## The two halves, and why they are separate

```
collect_pv_data()      reads PVs, reads the crosshair file, assesses.  MOVES NOTHING.
collect_image_data()   drives the zoom through all eight levels and takes images.
```

**Keep the split.** `collect_image_data` is the only place in this module that
commands hardware (`self.zoom_pv.put()`), and it carries a `WARNING:` in its
docstring for that reason. Anything that only needs to record a value belongs in
`collect_pv_data` — the crosshair positions were added there, and a test asserts
on the source that they stay there.

Practically, that means the first wizard page can be run any time, which makes it
useful for checking a change without stepping the zoom. The page that collects
images does move the beamline, and the wizard asks the operator to confirm it is
safe before that step.

## What it reports

Twenty-one parameters. The ones with history worth knowing:

- **`FLUX`** — compared with yesterday after normalising to 100% transmission,
  because staff work at whatever transmission suits the day. Limits are a
  percentage change, not an absolute flux. Measured day-to-day variation at
  constant transmission is about 1.3%, so 10% is generous.
- **`PID_XBPM1_X_KP`** — an absolute ceiling, not just change detection. A gain
  that is too large makes the feedback chase a beam that has already moved, which
  at low energy reinforces the vibration and loses the beam. It drifts upward
  because the EDM screen will not accept a value below 1e-5, so the safe value can
  only be restored with a `caput`.
- **`BEAM_SIZE_X/Y`** — the readback depends on the energy, so this is really
  "are we at the default CRL setting and the expected energy". (30, 19) on 177 of
  191 recorded setups.
- **`TRANSMISSION`** — 100% is *danger* on purpose. At full beam the camera and
  scintillator saturate, so the crosshair the staff member picks cannot be
  trusted. Do not relax this.
- **`Crosshair_positions`** — where the crosshair sits at each zoom level, read
  from `display.configuration`. Listed in `hidden_parameters`: stored for later
  analysis, never shown in the report or the eLog.

## Things that will catch you out

- **`display.configuration` is the master, for now.** The crosshair definitions
  are migrating to EPICS PVs, but the two can be out of sync. `get_zoom_dict()` is
  the only thing that parses that file — keep it that way, so the eventual switch
  is one change. Do not read the PVs while the file is still authoritative.
- **`custom_flux` needs two parameters at once**, flux and transmission, so it
  cannot go through the generic engine and is handled in
  `_assess_normalised_flux`.
- **Normalising by transmission under-corrects at low transmission.** Median
  normalised flux is 9.8e11 at ≤10% and 1.17e12 at 100% — about 19% apart. That is
  attenuator calibration, not clipping. The 10/20% bands absorb it.

## Porting to another beamline

Copy `AlignBeam.i04.yaml` to `AlignBeam.<ID>.yaml` and change the PV prefixes,
the thresholds and `zoom_pv`. The beam size band is energy-specific, so it needs
i04-1's own numbers. i04-1 has a zoom camera but possibly a different mechanism,
so do not assume the zoom levels carry across.
