# BeamlineMessages

Prompts the staff member to review and update the beamline messages that users
see in GDA, and records that it was done.

## Files

| File | What it does |
|---|---|
| `BeamlineMessages.py` | Records the check. |
| `GUI_BeamlineMessages.py` | The wizard pages. |
| `BeamlineMessages.yaml` | The prompt text. |

## What it is

Text and a confirmation, like InitialChecks. No PVs, no thresholds, nothing
beamline-specific — which is why it has no `.i04.yaml` and needs none.

Safe to run at any time; it touches no hardware.
