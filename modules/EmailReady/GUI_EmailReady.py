import random
import sys

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QGroupBox,
    QRadioButton,
    QDialogButtonBox,
    QApplication,
)


class TemplateSelectionDialog(QDialog):
    """
    A dialog window that allows the user to select an email template style.
    This dialog is built entirely from the configuration passed to it,
    with no hardcoded descriptions or filenames.
    """

    def __init__(self, email_styles_config, parent=None):
        """
        Initializes the dialog based on a configuration structure.

        Args:
            email_styles_config (list): A list of dictionaries, where each
                dictionary defines a style option for the dialog.
        """
        super().__init__(parent)
        self.setWindowTitle("Choose Email Style")

        # --- Data stores populated from the configuration ---
        # For 'random_choice' types, maps the ID to its list of templates
        self.random_pools = {}
        # For standard types, maps the ID to its single template filename
        self.id_to_template_map = {}

        # --- Layouts and Widgets ---
        self.layout = QVBoxLayout(self)
        self.groupBox = QGroupBox("Select the email template to generate:")
        self.radio_button_layout = QVBoxLayout()
        self.radio_buttons = []

        # --- Build the UI from the configuration ---
        for style_config in email_styles_config:
            style_id = style_config.get("id")
            description = style_config.get("description")

            if not (style_id and description):
                continue  # Skip invalid entries

            # Check if this is a random choice pool
            if style_config.get("type") == "random_choice":
                self.random_pools[style_id] = style_config.get("templates", [])
            else:
                # Otherwise, it's a standard template mapping
                self.id_to_template_map[style_id] = style_config.get("template")

            # Create the radio button for this style
            radio_button = QRadioButton(description)
            radio_button.setProperty("style_id", style_id)  # Store the unique ID
            self.radio_button_layout.addWidget(radio_button)
            self.radio_buttons.append(radio_button)

        # Select the first radio button by default
        if self.radio_buttons:
            self.radio_buttons[0].setChecked(True)

        self.groupBox.setLayout(self.radio_button_layout)
        self.layout.addWidget(self.groupBox)

        # --- OK and Cancel Buttons ---
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox)

    def get_selected_style_id(self):
        """
        Returns the unique style ID of the selected radio button.
        """
        for radio_button in self.radio_buttons:
            if radio_button.isChecked():
                return radio_button.property("style_id")
        return None
