# Modules

Each directory here is one step in the morning QC checklist. A module gathers a
few numbers or images, decides whether they are good, writes the result to redis,
and the report at the end collects them.

This file describes what every module has in common. Each module's own
`README.md` covers only what is specific to it.

## Adding a module

Drop in a directory, name it in `configure_blsetup.yaml`, and make sure the main
UI has widgets named after it. Nothing else is wired by hand — the application
imports what the top-level config names, and the GUI hides buttons for modules a
beamline has not declared.

The twelve currently live are AlignBeam, BeamlineMessages, BeamstopAlignment,
Close, CreateDirectories, CreateReport, EmailReady, InitialChecks, RemoteAccess,
RotationAxis, SampleLoad and TestCrystal. Directories not in that list
(`BeamCentre`, `Comment`, `CryoJet`, `Snapshot`, `TestStream`) are not loaded;
their READMEs say what they were.

## The files in a module

| File | What it is |
|---|---|
| `<Name>.py` | The work. A subclass of `MOD_Base` from `base/Modules.py`. |
| `GUI_<Name>.py` | A QWizard subclass. Page text comes from the YAML, not from here. |
| `<Name>.yaml` | Everything that is the same on any beamline: wizard text, which checks exist, report layout. |
| `<Name>.<ID>.yaml` | Everything true only on one beamline: EPICS addresses, instrument paths, thresholds. Optional. |

Some modules name their YAML after the GUI file rather than the module
(`GUI_RemoteAccess.yaml`); where that happens the GUI class sets
`config_basename`.

## How configuration is resolved

The shared file is loaded, then the file for the current beamline is deep-merged
over it, then `{BEAMLINE}` is replaced everywhere. All of that happens once, in
`BaseGUI.read_config`.

Three consequences worth knowing:

- **An override only states what differs.** Everything else is inherited.
- **A key set to `null` in an override is removed.** That is how a beamline
  without a given device drops a check entirely rather than having a mapping
  invented for it — i04-1 has a goniometer rather than a smargon, so its
  RotationAxis override deletes `smargon_home_age_check` and the `STUB_*` rules.
- **Never write a beamline's addresses in the shared file.** A test walks every
  shared file and rejects a `BL04I-` prefix or a `/dls_sw/i04/` path. Write
  `{BEAMLINE}` in paths and they resolve themselves.

## What the top-level config says about a module

From `configure_blsetup.yaml`:

```yaml
AlignBeam:
  widget2update: DE          # which widget on the main window reflects this module
  criteria2expire: [8, hour] # how long its result stays valid before the GUI nags
  needs_folder_to_write: True
```

`widget2update` is `DE` for a date field or `CB` for a checkbox. `criteria2expire`
drives the colouring on the main window, and is unrelated to any threshold in the
module's own YAML.

## Assessment rules

A module that judges numbers has an `assessment_rules` block. Every rule names a
check type and its limits:

```yaml
assessment_rules:
  BEAM_SIZE_X:
    check_type: 'range'
    limits: [29.5, 30.5, 28.5, 32.5]   # good_min, good_max, warn_min, warn_max
```

The check types are defined once, in `CHECK_SPECS` at the top of
`base/Modules.py`, along with how many limits each needs and how they must be
ordered. A malformed rule is reported as *unassessed* with a logged reason — never
as `danger`, because a configuration mistake must not look like a beamline fault.

`greater_than` and `less_than` take `[good, warning]`. The deadband family
compares with yesterday. `equals` takes a `good_value`, and optionally
`mismatch_status: warning` where a mismatch is a thing to fix rather than an
alarm. `range`/`in_range` take four limits.

## Other YAML blocks you will meet

| Block | Meaning |
|---|---|
| `PVs` | `{prefix: {report_name: suffix}}`. The report name is what appears in the table and in `assessment_rules`. |
| `string_pvs` | PVs whose value is genuinely text. Everything else is read raw, so comparisons see the number the IOC holds rather than the rounded one the EDM screen shows. |
| `hidden_parameters` | Stored and assessed, but kept out of the report and the eLog. For values recorded for later analysis. |
| `WP<n>_Label_<n>_Text` | The wizard page text. HTML is allowed. Beamline-independent by default; an override can replace it where a beamline does the step differently. |
| `report_table_title` | The heading above this module's table in the report. |

## Two things to know when working on a module

**Know which methods command hardware.** Most modules only read. Two — AlignBeam
and RotationAxis — also move things: AlignBeam steps the zoom through its levels
to photograph the beam, and RotationAxis turns omega to photograph the pin. That
is what the module is for, and the wizard tells the operator to make sure it is
safe to move before they press Next.

What matters when *editing* one is that the two halves stay apart. Each of those
modules keeps the code that only reads in a separate method from the code that
moves, so anything that merely records a value can be added to the first without
touching the second. Both of those methods say so in their docstring.

Note also that a move does not have to look like one: `cameras.zoom.set()` and
`motors.omega.move()` go through `beamline` library device objects and read as
ordinary attribute access, so **grepping for `caput` will not find them**.

**Not assessable is not the same as passing.** A check that compares with
yesterday returns no status at all when there is nothing to compare against — on
the first run after a parameter is renamed, for instance. It never falls back to
`good`, because a silent pass hides exactly the day you would want to look at.

## Testing

`tests/` at the repository root, run with `python3 -m pytest tests/`. Module
rules are tested against the real shipped YAML, so editing a limit shows up
there. See `tests/README.md`.
