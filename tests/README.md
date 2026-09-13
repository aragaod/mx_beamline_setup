# Tests

Validation tests for the beamline setup QC checks. They cover the assessment
engine on `base/Modules.py` and the `assessment_rules` blocks in every module's
YAML — that is, the code that decides whether a number is green, amber or red.

Nothing here touches the beamline. Every test is pure arithmetic on values held
in the test file or read from the shipped YAML. No PV is read and **no PV is ever
written** — see the operating constraint at the top of `PROGRESS.md`.

## Running them

```bash
source /dls/science/groups/i04/setup_i04_edge.sh   # puts PYTHON3.12 on PATH
cd /dls/science/groups/i04/Python/applications/beamline_setup

python3 -m pytest tests/                  # everything
python3 -m pytest tests/ -q               # everything, one line of output
python3 -m pytest tests/ -v               # one line per test
```

Narrowing down, which is what you want when a single row in the report is wrong:

```bash
python3 -m pytest tests/validation/test_alignbeam.py          # one file
python3 -m pytest tests/validation/test_alignbeam.py -k flux  # one subject
python3 -m pytest tests/test_assess_helpers.py::test_flux_absolute_boundaries
python3 -m pytest tests/ -k "beam_size or transmission"       # several subjects

python3 -m pytest tests/ -x               # stop at the first failure
python3 -m pytest tests/ --lf             # rerun just what failed last time
```

`-k` matches against the test name, and the names are written to be searched:
`test_<parameter>_<condition>`, for example `test_flux_drift_within_10pc_is_good`
or `test_beam_size_x_31um_is_warning`. So `-k flux` finds every flux case
wherever it lives, and a failure report reads as a list of beamline conditions
rather than a list of function names.

## Layout

```
tests/
├── conftest.py               fixtures; the harness that unbinds the engine from
│                             Config, redis and the GUI
├── test_assess_helpers.py    the helpers on Base, at their boundaries
├── test_yaml_rules.py        every assessment_rules block in the repository
├── fixtures/                 sample processing logs, for the parser tests
└── validation/
    ├── test_alignbeam.py     one file per module, against its real YAML
    ├── test_testcrystal.py
    ├── test_rotationaxis.py
    ├── test_qualitycontrol_parser.py
    ├── test_per_image_diagnostics.py
    └── test_xia2_parser.py
```

## What each test file covers

| File | Covers | Would catch |
|---|---|---|
| `test_assess_helpers.py` | `assess_greater_than`, `assess_less_than`, `assess_in_range`, `assess_deadband`, `assess_abs_limit_and_change` — each on its limit as well as either side, plus non-numeric input, `None`, and empty or wrong-length limits | a boundary that is off by one comparison, a helper that reports `danger` for input it simply cannot read, a deadband that treats "no history" as a pass |
| `test_yaml_rules.py` | Walks every `assessment_rules` block: each rule must name a check type the engine implements, carry the right number of limits in the right order, and have a `good_value` where one is required. Also loads every module YAML with a duplicate-key detector, and checks every rule can be described for the report | a check type no dispatcher implements (silently no-op before), a one-element `limits` list (V1), reversed limits (V3), a repeated key that YAML discards (V2) |
| `validation/test_qualitycontrol_parser.py` | The fast_dp and aimless log parsers against real log excerpts in `fixtures/`: which of the three shells (Overall / InnerShell / OuterShell) each statistic comes from, that labels sharing a prefix cannot claim each other's values, and that a missing file warns rather than crashes | a log format change silently yielding a wrong number, `Rmeas` picking up `Rpim` or `Rmerge`, `Completeness` picking up the anomalous line |
| `validation/test_per_image_diagnostics.py` | The INTEGRATE.LP per-image metrics: that a decoy ten-column table is not read as image rows, that a smooth absorption swing is *not* flagged while a discontinuity is, that the step is located as well as measured, and the thresholds against measured medians | someone changing the scale metric back to deviation-from-median, which does not discriminate; a step going unreported or unlocated |
| `validation/test_xia2_parser.py` | The xia2.dials and xia2.3dii parsers against real merging-statistics fixtures: that the resolution matches the published summary rather than the low-resolution limit, that keys are prefixed so they cannot be judged against fast_dp's thresholds, and that a pipeline which has not run is not an error | the inverted min/max naming in the JSON silently reporting 54 Å as the resolution; a missing pipeline raising at setup time, when fast_dp finishes first |
| `validation/test_testcrystal.py` | TestCrystal's five rules against its YAML, and that every assessed parameter is one the parser actually produces | a rule assessing a key nothing parses, the ten-rows-for-five-measurements duplication returning |
| `validation/test_alignbeam.py` | AlignBeam's shipped rules end to end: both XBPM feedback PVs present and assessed, flux normalised to 100% transmission before comparison, beam size bands, full-beam transmission still red, PID gain ceiling and change detection, and that the engine marks "no history" rather than passing | a limit edited in the YAML without thinking through what it means, the XBPM1 row disappearing again, someone relaxing the 100%-transmission check or the PID ceiling |
| `validation/test_beam_present_checks.py` | That AlignBeam refuses to photograph a dark beamline (F12): scintillator in, both shutters open and flux present are all read and assessed, the module stops before driving the zoom when any of them says the beam is not there, and the message names which one | the `FIXME - I am not checking for shutter opened, scintillator up and flux is okish` returning; a dark field being stepped through eight zoom levels and reported as an alignment |
| `validation/test_alignbeam_partial_failure.py` | That a dead OAV camera costs the images and nothing else: PVs are read and the report is written even when the image step raises, and the camera is tested before the zoom is driven rather than after | the whole morning's record being lost because the camera IOC was down, as happened on 2026-08-31 |
| `validation/test_crosshair.py` | The crosshair position: that it is recorded on the safe PV path and never requires driving the zoom, and that it stays a hidden parameter rather than appearing in the eLog table | the recording drifting onto the image path, which would make a stored number depend on moving the beamline |
| `validation/test_rotationaxis_montage.py` | Recovering the four frames from a stored montage and measuring the rotation axis (B4): the tiling geometry, the drawn crosshair found by colour rather than position, pin-tip detection against dust, Otsu surviving the white angle label, and that an equal-and-opposite pair reads as perfectly centred. Runs against every stored montage when they are reachable | a frame cropped one pixel out, which still looks like a pin image; dust taken for the tip, which gave exactly 0.00 on all 33 days; a threshold that calls the whole frame dark; measuring against the crosshair instead of the pair, which would call a centred axis misaligned |
| `validation/test_rotationaxis.py` | RotationAxis's rules against its real YAML | a rule referring to a check type or a parameter that no longer exists |
| `validation/test_remote_access_sessions.py` | The local/remote split (B5): a `-` remote address marks a console session on a beamline machine, those are listed separately, and no ipinfo or DNS lookup is attempted for them | the post-NoMachine-upgrade regression where three console sessions read as three people connected from outside |
| `validation/test_test_sample_identity.py` | Which protein was measured, and whether the indexing agrees: identification from the sample name and by unit-cell fingerprint when the name is unhelpful, the space group and cell-deviation checks, and the registry in `TestCrystal.yaml` | ISa and Rmeas being presented as beamline quality when they in fact describe a failed indexing, as on 2026-08-11 |
| `validation/test_report_order_and_gaps.py` | That the report follows checklist order and states which modules were not run (F1) | sections in whatever order redis returned; a skipped module looking identical to one that does not exist |
| `validation/test_nothing_found_messages.py` | That SampleLoad and BeamstopAlignment say so when they find nothing | "nothing was there" being indistinguishable from "everything was fine" |
| `validation/test_email_templates.py` | That all 33 user email templates render, with the values the app actually supplies | a template broken by markdown-style escaping inside a Jinja expression, invisible until the day it is picked |
| `test_layered_config.py` | The layered-YAML resolver: deep merge of `<Module>.<beamline>.yaml` over `<Module>.yaml`, `null` in an override removing a key rather than blanking it, and that every module still resolves to what it did before the layering | i04-1 being unable to delete a check it has no hardware for; a merge that overwrites a whole nested block instead of merging it |
| `test_module_gui_classes.py` | That every module's `GUI` class imports and carries `read_config` | the seven classes that silently lost `read_config` when it moved to `BaseGUI` - every one failing at the moment its button was pressed, with the whole suite green |
| `test_hidden_parameters.py` | Hidden parameters (V13): still stored, still assessed, still logged, but kept out of the rendered table - and the `format_version` stamp on every stored report | a value that only exists for later analysis being pushed in front of staff every morning; reports going out unstamped and becoming unmigratable |
| `test_versioned_images.py` | That re-running a module keeps the previous image (B6), named with the time the displaced file was written rather than now | the second run of a module overwriting the image that showed what was wrong the first time |
| `test_dose.py` | The arming-log reader and the dose scaling (B2b): the duplicate `Aborted` record that would double every dose, one API call per beam configuration, dose refused rather than scored zero when flux or exposure is missing, and crystal identity matched on token boundaries | `Sethau1` silently absorbing `Sethau13`'s dose; the two over-dose mornings being lost because they were filed under `test-shots/`; a missing flux quietly lowering a crystal's lifetime total; a user's `Ins_14` being reported as a test crystal because it matches the `insulin` alias |
| `test_report_archive.py` | Reading the stored reports back as a table (F8): what is and is not a report key, values held as display strings by pre-migration reports, booleans deliberately not counted as numbers, day-pairing between two modules that ran on different subsets of days, and the correlation and fit against cases with known answers - including reproducing the published r = -0.84 for dose against ISa | a parameter silently dropping out of a series; a flat series dividing by zero mid-scan; comparing two modules without stating how few days actually have both |
| `test_self_calls_resolve.py` | Walks the AST of every module and asserts that each `self.name()` a class calls actually exists on that class | the three crashes of 2026-08-31 - a method placed on a sibling `Base`, a helper placed on the wrong class in the same file, and `QtWidgets` used without being imported. `py_compile` sees none of them, because the line only resolves when it runs |
| `test_oncall_log.py` | The on-call log (F2): one hash field per person per day, both timestamps joining one record, weekends flagged, a year's expiry, and that a dead or corrupt redis is logged and swallowed - plus `dev/oncall_report.py`'s month, person and weekend counting | bookkeeping blocking a setup at login; a corrupt entry losing the day it was meant to record; the report miscounting the weekend days a claim is made from |
| `test_redis_migration.py` | `dev/migrate_redis_reports.py`: key renames, string-to-number conversion and the format stamp, with two invariants - statuses are never rewritten, and nothing that is not a report is unpickled | the migration replacing the PyQt `*_lastrun` objects with `None`, which it did until this caught it; a rewritten status destroying the audit trail of what staff saw |
| `test_module_readmes.py` | That every module directory has a README and that its Files table, override filenames and active/inactive claims still match the directory | a README naming a file that has been deleted, or calling a live module inactive |

## Per-parameter thresholds

This table is the human-readable version of the criteria, which otherwise exist
only inside the module YAML files. Keep it in step with them.

| Parameter | Module | Check | Good | Warning | Danger |
|---|---|---|---|---|---|
| `FLUX` | AlignBeam | drift vs yesterday, normalised to 100% transmission | ≤ 10% change | ≤ 20% | > 20% |
| `TRANSMISSION` | AlignBeam | range | 6–35 % | 4–51 % | outside. 100% is an error: it saturates the camera and scintillator, so the crosshair cannot be trusted |
| `BEAM_SIZE_X` | AlignBeam | range | 29.5–30.5 µm | 28.5–32.5 | outside |
| `BEAM_SIZE_Y` | AlignBeam | range | 18.5–19.5 µm | 17.5–20.5 | outside |
| `PID_XBPM1_X_KP` | AlignBeam | absolute ceiling + change | unchanged and \|v\| ≤ 8e-6 | changed, or \|v\| above 8e-6 | \|v\| ≥ 1e-5 — the aggressive value that oscillates at low energy |
| `PID_XBPM1_Y_KP`, `PID_XBPM2_*_KP` | AlignBeam | change only | unchanged | changed | — (awaiting a ceiling from the diagnostics group) |
| `Feedback_enable` | AlignBeam | equals | `Run` | — | anything else |
| `Feedback_XBPM1_good`, `Feedback_XBPM2_good` | AlignBeam | equals | `1` | — | anything else |
| `Machine_X_STEER`, `Machine_Y_STEER` | AlignBeam | change vs yesterday | unchanged | change ≤ 2 | change > 2 |
| `S4_slits_X`, `S4_slits_Y` | AlignBeam | ≥, plus change | ≥ 0.8 mm | ≥ 0.5, or changed | < 0.5 mm |
| `DCM_roll`, `DCM_pitch` | AlignBeam | change vs yesterday | ≤ 0.5 | ≤ 1.0 | > 1.0 |
| `DCMP_temp1` | AlignBeam | change vs yesterday | ≤ 2% | ≤ 5% | > 5% |
| `ISa` | TestCrystal | ≥ | ≥ 35 | ≥ 25 | < 25 |
| `Resolution` | TestCrystal | ≤ | ≤ 2.0 Å | ≤ 2.5 | > 2.5 |
| `Aimless_Rmeas_low_res` | TestCrystal | ≤ | ≤ 0.030 | ≤ 0.036 | > 0.036 |
| `CChalf` | TestCrystal | ≥ | ≥ 0.9 | ≥ 0.7 | < 0.7 |
| `Completeness` | TestCrystal | ≥ | ≥ 97% | ≥ 94% | < 94% |
| `STUB_X/Y/Z` | RotationAxis | change vs yesterday | ≤ 0.001 | ≤ 0.003 | > 0.003 |
| `GONP_Y`, `GONP_Z` | RotationAxis | change vs yesterday | ≤ 0.003 | ≤ 0.010 | > 0.010 |
| `GONP_X` | RotationAxis | range | ±0.0001 | ±0.0005 | outside |
| `Smargon_home` | RotationAxis | time since | < 8 h | < 18 h | older |
| `Scale_step_pct` | TestCrystal | ≤ | ≤ 4.0 % | ≤ 6.5 % | > 6.5 % — largest jump in per-image scale between adjacent 25-image windows. Measured across 55 datasets: median 2.4, p90 4.0, p99 6.4 |
| `Rejects_worst_image` | TestCrystal | ≤ | ≤ 14 | ≤ 25 | > 25 — rejected observations on the worst image, above the dataset median |
| `Spot_prediction_sd_px` | TestCrystal | ≤ | ≤ 0.80 px | ≤ 1.20 | > 1.20 — how well the prediction model fits the spots |
| `Goniometer_speed_sd_deg` | TestCrystal | ≤ | ≤ 0.20° | ≤ 0.45 | > 0.45 — whether omega turned at constant *speed*, not axis alignment |
| `BS_X_*`, `BS_Y_*`, `BS_Z_*` | BeamstopAlignment | change vs yesterday | ≤ 0.011 / 0.021 / 0.05 | ≤ 0.021 / 0.041 / 0.1 | above |

## Two rules for writing tests here

**Recompute, never trust a stored status.** The reports in redis carry the status
that was calculated under whatever limits were in force on the day they were
written, and the limits have changed since. A test that asserts on a stored
status is testing history, not the code. Read values from redis if you like;
always recompute the verdict.

**Not assessable is not the same as passing.** A rule that compares with
yesterday returns no status at all when there is no previous report, and the
tests assert on that explicitly. If a change ever makes those cases come back
`good`, a red row will start hiding behind the first day of a run.

## Adding a case

To cover a new parameter, add it to `tests/validation/test_<module>.py` using the
module's real YAML through the `load_module_yaml` fixture, so the test follows the
shipped limits rather than a copy of them. For a whole new module, add a file of
the same shape — `test_yaml_rules.py` will already be walking its YAML, so
malformed rules are caught before anyone writes a single case by hand.
