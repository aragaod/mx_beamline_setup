# Comment — not active

**This module is not loaded.** It is not named in `configure_blsetup.yaml`, so
the application never imports it and the GUI shows no button for it.

A free-text comment from the staff member, to go into the report.

Never wired up. If comments are wanted, the report template already has somewhere
to put them and `BeamlineMessages` is the closest working example of a
text-only module.

## If you want to bring it back

Name it in `configure_blsetup.yaml` with a `widget2update`, a
`criteria2expire` and whether it `needs_folder_to_write`, make sure the main UI
has widgets named after it, and give it a `GUI_Comment.py` and a `Comment.yaml`.
See `modules/README.md` for the anatomy.
