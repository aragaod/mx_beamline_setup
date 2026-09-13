# InitialChecks

A checklist of things to confirm before anything else: that the experiment is
authorised, that the hutch is clear, that the message of the day is current.

## Files

| File | What it does |
|---|---|
| `InitialChecks.py` | Records that the checks were done. |
| `GUI_InitialChecks.py` | The wizard pages. |
| `InitialChecks.yaml` | The checklist text. Everything this module does is here. |

## What it is

Text and a confirmation. There are no PVs, no thresholds and no
`assessment_rules` — the value is in making a human read the list and tick it,
and in recording that they did.

That makes it the **best first module to run when testing**: it exercises the GUI,
config loading and the redis write, and touches no hardware at all.

## Editing it

The checklist lives entirely in `InitialChecks.yaml` as wizard page text, so
changing what staff are asked is a YAML edit and needs no code change. HTML is
allowed.

The paths mentioned in the text use `{BEAMLINE}` — the motd path used to be a
hardcoded `/dls_sw/i04/etc/motd`, which would have told i04-1 staff to edit i04's
file. Keep new paths written the same way.
