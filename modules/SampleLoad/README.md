# SampleLoad

Records what is in the robot dewar: which pucks are loaded, where, and a
photograph of the dewar plus an image of each puck.

## Files

| File | What it does |
|---|---|
| `SampleLoad.py` | Reads the robot PVs, fetches images, builds the report. |
| `GUI_SampleLoad.py` | Wizard pages and the puck table. |
| `SampleLoad.yaml` | Wizard text, file-age policy, the blocked-positions warning. |
| `SampleLoad.i04.yaml` | i04's robot PVs, the logistics host, the blocked-positions file. |

## Where the data comes from

- **Robot PVs** for what is in each position.
- **`proposal_positions.json`** for which proposal owns which puck. The path is
  already written with `{BEAMLINE}`, so it resolves itself.
- **The logistics service** for the dewar photograph and the puck images. The host
  is i04-specific and lives in the override — `i04-1-logistics` does respond, but
  whether it is populated is an open question.

## Freshness, not thresholds

This module has no `assessment_rules`. What it checks instead is that the data is
recent: `json_file_age_check` and `image_age_check` both default to 12 hours, via
`check_file_age` and `check_age_from_filename` on `MOD_Base`. A stale dewar photo
is worse than none, because it looks current.

Those two blocks are generic policy rather than i04 physics, so they stay in the
shared file.

## Things that will catch you out

- **Image filenames are fixed per module**, so re-running overwrites the previous
  image. That is backlog item B6.
- **`blocked_positions_file`** is a hardcoded `/dls_sw/i04/` path, which is why it
  sits in the override rather than the shared file.
- The puck images are fetched one per barcode, so a dewar with many pucks makes
  many requests.

## Open work

**F3**, detecting which puck positions actually contain a pin, is a separate
project on its own timeline and feeds a reconciliation script owned elsewhere. It
should not absorb porting effort.
