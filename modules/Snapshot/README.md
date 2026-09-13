# Snapshot — not active

**This module is not loaded.** It is not named in `configure_blsetup.yaml`, so
the application never imports it and the GUI shows no button for it.

Capturing a snapshot image, presumably of the sample or the beam.

Never wired up. Note that `UIs_py/Graphical_User_Interface_2025.py` — a second,
unused copy of the main UI — differs from the live one only by replacing
`RobotSamples` with `Snapshot`, which suggests this was once intended to replace
a button. Whether that UI variant should exist at all is an open question in
`PROGRESS.md`.

## If you want to bring it back

Name it in `configure_blsetup.yaml` with a `widget2update`, a
`criteria2expire` and whether it `needs_folder_to_write`, make sure the main UI
has widgets named after it, and give it a `GUI_Snapshot.py` and a `Snapshot.yaml`.
See `modules/README.md` for the anatomy.
