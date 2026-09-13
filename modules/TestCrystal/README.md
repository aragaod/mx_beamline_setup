# TestCrystal

Reads the processing results from the morning's test crystal collection and
judges the diffraction quality. Collects no data itself — the staff member runs
the collection in GDA and points this module at the master file once fast_dp has
finished.

## Files

| File | What it does |
|---|---|
| `TestCrystal.py` | Orchestrates and assesses. |
| `QualityControl.py` | All the parsing. The substance of this module. |
| `ImageManipulation.py` | Builds the diffraction image montage. |
| `GUI_TestCrystal.py` | Wizard pages and the master file chooser. |
| `TestCrystal.yaml` | Wizard text, the **test sample registry**, and the identity checks. |
| `TestCrystal.i04.yaml` | i04's quality thresholds, and where the dose service lives. |

Dose is calculated by two files in `base/`, because the dev analysis tools use
the same machinery: `base/eiger_log.py` reads the detector arming log, and
`base/dose.py` turns a collection into MGy.

## Where the numbers come from

```
<processing dir>/fast_dp/CORRECT.LP     ISa, space group, unit cell
                        fast_dp.log     resolution, CC½, completeness, multiplicity
                        aimless.log     Rmeas, per-batch Rmerge
                        INTEGRATE.LP    per-image scale, mosaicity, spot and spindle errors
```

**`aimless.log` here is fast_dp's own scaling step**, not an independent pipeline —
fast_dp runs XDS, then pointless, then aimless. That is why the report shows five
measurements rather than ten: every `Aimless_*` row used to duplicate a fast_dp
number.

**Statistics are parsed by named column, never by character position.** Both logs
report Overall / InnerShell / OuterShell and each field states which shell it
wants. Before 2026-08-31 this used fixed slices like `[-12:-6]`, so which column a
value came from was invisible from the code — `Rmerge` read the inner shell purely
by accident of where the slice landed.

Rmeas is the number ISPyB shows and the one the wizard text judges on, which is
why it is the R-factor kept.

## The test sample registry

The wizard says "insulin", but i04 rotates through at least six test proteins.
`test_samples` in the **shared** YAML — the proteins are the same on any beamline —
maps each to its aliases, usual space group and usual cell.

**Identity comes from the master file path, never from the space group.** That is
deliberate: inferring identity from the space group would be circular, because a
thaumatin that indexed as `P 1` would read as "unknown sample" instead of
"thaumatin indexed wrong", losing the signal on exactly the days it matters.

To add a sample, add an entry. Aliases are plain case-insensitive substrings, not
regular expressions, matched against the whole path; add every naming people have
actually used. They must be unique across samples, and a test enforces it.

Two forms of space group are handled, because the pipelines differ. fast_dp gives
a **number**, and it is the point group — 89 for thaumatin, not the 92 of P41212.
xia2 gives a **name**, and the same pipeline gives more than one name for the same
protein (dials assigns thaumatin `P 41 21 2` on 24 runs and `P 4 21 2` on 13, the
second being the point group with the screw axis unresolved), which is why
`accepted_space_groups` is a list.

> The accepted lists are seeded from what the archive contains, which is evidence
> of what the pipelines *do*, not of what is crystallographically correct. They
> need confirming against the literature.

An unrecognised sample is recorded, not rejected: the space group and cell are
kept with no verdict, and `Test_sample_identified` warns — a gap in configuration,
not a fault on the beamline — until someone adds it.

`Sample_looks_like` appears when the path says one protein but the space group and
cell match another cleanly. That means the wrong sample was mounted or it was
mislabelled; the data itself is fine, so users still get their normal email and
this is for staff.

## Dose, and why ISa alone is misleading

This module reports ISa and Rmeas as a measure of how the beamline is doing. A
test crystal's ISa falls steadily as it ages, whatever the beamline is doing.

Over July and August 2026 the test crystal's ISa fell from about 41 to about 31
and the report presented that as the beamline degrading. It was not. Cumulative
dose against ISa over those 17 setups gives r = -0.84 - roughly 70% of the
decline was the crystal ageing exactly as it should.

So the report carries two dose rows:

| Parameter | What it says |
|---|---|
| `Dose_this_collection_MGy` | What this dataset delivered. The module asks for 1.5 MGy. |
| `Dose_crystal_lifetime_MGy` | Everything this crystal has absorbed this visit. 30 MGy is the Garman limit. |

The per-collection row earns its place on its own. On 31 July and 2 August 2026
the setup collections ran at 71% transmission instead of the usual 35%,
delivering just over double the intended dose; 6.4 MGy of that crystal's 33.4 MGy
lifetime came from those two mornings and nobody noticed at the time.

Nothing new is measured. The eiger arming log already records flux, energy, beam
size and exposure at the moment of arming, and RADDOSE-3D is already a service
(`applications/autodose`). Dose is linear in flux and exposure, so the service is
asked once per beam configuration and the rest is arithmetic - two calls covered
a whole month of collections.

**It never fails the module.** An unreachable service or a missing arming record
leaves a `Dose_note` row explaining why, and every other parameter is reported as
normal. A dose column is worth having and is not worth losing a morning's report
over.

`dev/trends.py` reads the same machinery for the questions that need more than
one morning: one crystal's whole life, every crystal's lifetime dose, and any
stored parameter against any other.

## Why identity matters more than it looks

On 2026-08-11 the reported dataset indexed as space group 3 instead of 89 with a
52% cell deviation, and the report showed `ISa 3.51`, `Rmeas 0.161`. Those look
like a dead crystal or a bad beamline and are neither — they describe a failed
indexing. Across the archive, thaumatin indexed away from its usual space group on
2 of 236 runs and carbonic anhydrase on 3 of 116.

## The per-image diagnostics

`Scale_step_pct` is the largest jump in per-image scale between adjacent 25-image
windows — **a step, not a deviation from the median**. The scale legitimately
swings 16% or more as absorption changes with rotation, so deviation does not
discriminate at all; absorption is smooth and a beam dump is not.

`Goniometer_speed_sd_deg` measures whether omega turned at a constant *speed*. It
says nothing about whether the rotation axis is aligned.

## xia2

`parse_xia2` reads xia2.dials and xia2.3dii, which sit beside fast_dp. They are
**not in the daily table**: fast_dp is the fast one and this module runs the moment
it finishes, so the xia2 results usually do not exist yet. A missing pipeline is
normal and logs at info. Keys are prefixed with the pipeline because the pipelines
cut resolution differently — 1.26 Å from fast_dp against 1.08 from dials on the
same data — so each would need its own limits.

## Porting to another beamline

The registry and the identity checks are beamline-independent and stay in the
shared file; only the quality thresholds are in the i04 override. Whether these
statistics mean the same thing on a pilatus, fixed-energy beamline is an open
question in `PROGRESS.md`.
