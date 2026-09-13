import os

import yaml as config_loader
from PyQt5 import QtWidgets, QtCore

from beamline import ID


def deep_merge(base, override):
    """Merge `override` onto `base`, recursing into nested dictionaries.

    A key whose override value is null is *removed*. That is not a nicety: i04-1
    has a goniometer rather than a smargon, so its RotationAxis override needs to
    delete `smargon_home_age_check` and the `STUB_*` rules outright, not re-value
    them. Anything else - a list, a scalar - replaces wholesale, because a
    per-beamline PV block or limits list should be stated in full rather than
    merged element by element.
    """
    merged = dict(base)
    for key, value in (override or {}).items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def substitute_beamline(value, beamline):
    """Fill {BEAMLINE} in every string in a nested structure.

    Modules used to each call .format(BEAMLINE=self.ID) on the handful of paths
    they happened to remember, so a path added later silently kept the literal
    placeholder. Doing it once over the whole config removes that class of bug.
    """
    if isinstance(value, str):
        return value.replace("{BEAMLINE}", beamline) if "{BEAMLINE}" in value else value
    if isinstance(value, dict):
        return {k: substitute_beamline(v, beamline) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_beamline(v, beamline) for v in value]
    return value


class BaseGUI(object):
    """
    Common GUI functionality mixin.
    Inherit from this in your GUI_*.py classes to gain helper methods.
    """

    # Set in a module's GUI class when the YAML is not named after the module,
    # as with GUI_RemoteAccess.yaml and GUI_CreateReport.yaml.
    config_basename = None

    def config_directory(self):
        """Where this module's YAML files live: the module's own directory."""
        import inspect

        return os.path.dirname(inspect.getfile(self.__class__))

    def config_paths(self, beamline=None):
        """The shared default and this beamline's override, in merge order.

        Layered so that one beamline's PVs and limits never sit in the file
        another beamline reads:

            RotationAxis.yaml         what the check is - beamline independent
            RotationAxis.i04.yaml     i04's PVs, paths and thresholds
            RotationAxis.i04-1.yaml   i04-1's, when it exists

        The base file is required; the override is optional, so a module with
        nothing beamline-specific needs only one file.
        """
        beamline = beamline or ID
        directory = self.config_directory()
        stem = self.config_basename or type(self).__module__.split(".")[-1].replace(
            "GUI_", ""
        )
        return (
            os.path.join(directory, f"{stem}.yaml"),
            os.path.join(directory, f"{stem}.{beamline}.yaml"),
        )

    def read_config(self, beamline=None):
        """Load the shared default, merge this beamline's override over it.

        Replaces eight identical copies of this method, one per module, each of
        which hardcoded its own filename and did no substitution.
        """
        beamline = beamline or ID
        base_path, override_path = self.config_paths(beamline)

        with open(base_path) as handle:
            config = config_loader.load(handle, Loader=config_loader.FullLoader) or {}

        if os.path.exists(override_path):
            with open(override_path) as handle:
                override = (
                    config_loader.load(handle, Loader=config_loader.FullLoader) or {}
                )
            config = deep_merge(config, override)

        self.config = substitute_beamline(config, beamline)
        return self.config

    def show_urgent_warning(
        self, parent_widget, title, text, informative_text, buttons
    ):
        """
        Displays a styled, urgent warning dialog.
        """
        msg_box = QtWidgets.QMessageBox(parent_widget)
        msg_box.setIcon(QtWidgets.QMessageBox.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setText(f"<b>{text}</b>")
        msg_box.setInformativeText(informative_text)

        # Shared Stylesheet for consistency across all modules
        style_sheet = """
            QMessageBox { background-color: #FFF3CD; border: 1px solid #FFEEBA; }
            QLabel { color: #664D03; font-size: 14px; }
            QPushButton { border: 1px solid #ADB5BD; border-radius: 4px; padding: 6px 12px; min-width: 90px; font-size: 13px; }
            QPushButton#proceedButton { background-color: #DC3545; color: white; font-weight: bold; }
            QPushButton#proceedButton:hover { background-color: #C82333; }
            QPushButton#editButton { background-color: #007BFF; color: white; }
            QPushButton#editButton:hover { background-color: #0069D9; }
            QPushButton#cancelButton { background-color: #6C757D; color: white; }
            QPushButton#cancelButton:hover { background-color: #5A6268; }
        """
        msg_box.setStyleSheet(style_sheet)

        for btn_text, btn_role, btn_id in buttons:
            button = msg_box.addButton(btn_text, btn_role)
            button.setObjectName(btn_id)

        msg_box.setWindowFlags(msg_box.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        msg_box.exec_()

        clicked_button = msg_box.clickedButton()
        return clicked_button.text() if clicked_button else "Cancel"
