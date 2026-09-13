# BeamstopAlignment

Records the beamstop position at each of the three detector distances and
compares it with yesterday.

## Files

| File | What it does |
|---|---|
| `BeamstopAlignment.py` | Finds the collections, assesses the positions. |
| `BeamstopAnalysis.py` | Image analysis and the montage. |
| `GUI_BeamstopAlignment.py` | Wizard pages. |
| `GUI_BeamstopAlignment.yaml` | Wizard text, plot options, search window. |
| `GUI_BeamstopAlignment.i04.yaml` | i04's eiger redis keys, beamstop distances, thresholds. |
| `investigate_redis.py`, `test_logic.py`, `test_consistency.py` | Ad-hoc debugging scripts, not part of the suite. |

The YAML is named after the GUI file rather than the module, so the GUI class
sets `config_basename`.

## How it finds the data

It reads the eiger arming log from redis — `i04:eiger:collections`, a list with
its schema in a companion key — and looks back `search_hours` for collections
matching each configured distance. Those keys are i04-specific and live in the
override; **i04-1 is a pilatus beamline, so the key will differ if it exists at
all.**

## What it reports

`BS_X/Y/Z` for each of high resolution, standard and low resolution, each
compared with yesterday. Z gets a looser limit than X and Y.

Until 2026-08-31 this module reimplemented the deadband comparison inline and
gated it on `isinstance(value, (int, float))`, so a position arriving as a string
was silently left unassessed. It now uses the shared engine, which coerces with
`float()`.

## Open work

**B1**, a figure of merit for alignment quality, is the one genuinely open design
question in the backlog — and it now has a specification and test data. Two
metrics: one from the beam-centre ROI asking whether beam reaches the detector and
whether the beamstop is centred, and one from the crosshair to the detector edge
asking whether the beamstop is itself diffracting a ring.

The standalone repository <https://github.com/aragaod/beamstop-qc> already
produces the 1D vertical, horizontal and diagonal scattering profiles those need,
and states it generates plots rather than metrics — so this is largely turning
existing profiles into two numbers. Labelled data exists: each alignment folder
holds the sequence of attempts with the last one good and the intermediate ones
bad, plus a published Zenodo test set (DOI 10.5281/zenodo.15739324).
