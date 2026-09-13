from base import MOD_Base
from .RA_ssh import Manage_NX_Connections
import getpass

from datetime import datetime
from PyQt5.QtWidgets import QWizard
from PyQt5 import QtCore

import pandas as pd

from modules.RemoteAccess.GUI_RemoteAccess import GUI
import pprint, logging


class RemoteAccess(MOD_Base):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.now = datetime.now()

    def launch_GUI(self):
        self.RemoteAccess_WZ = QWizard()
        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")
        self.ui.read_config()

        # TODO: implement display configuration and zoom in beamline library
        self.ui.config["display_configuration"] = self.ui.config[
            "display_configuration"
        ].format(BEAMLINE=self.ID)

        self.ui.setupUi(self.RemoteAccess_WZ)

        # Connecting the Finish and Cancel buttons so that they trigger update of status. (set_status_true() set_status_false() are defined in Modules.py/MOD_Base
        self.RemoteAccess_WZ.button(QWizard.FinishButton).clicked.connect(
            self.set_status_true
        )
        self.RemoteAccess_WZ.button(QWizard.CancelButton).clicked.connect(
            self.set_status_false
        )
        self.RemoteAccess_WZ.button(QWizard.NextButton).clicked.connect(self.next)

        self.RemoteAccess_WZ.button(QWizard.BackButton).clicked.connect(self.back)

        self.RemoteAccess_WZ.button(QWizard.FinishButton).clicked.connect(self.finish)

        # Handle pressing the top right X button
        self.RemoteAccess_WZ.rejected.connect(self.reject)

        # Lock main window to prevent other tasks
        self.RemoteAccess_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.RemoteAccess_WZ.show()

    def next(self):
        self.log.debug(
            f"Next button pressed. Collecting user information then going to next window."
        )
        return self.drive()

    def finish(self):
        self.log.debug(f"Finish button pressed. Module ended")

    def back(self):
        self.log.debug(
            "Back button pressed, maybe you want to collect rotation axis data again?"
        )

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()

    def log_df(self, list_of_lists):
        # 1. Handle the completely empty state gracefully
        if len(list_of_lists) <= 1:
            self.log.info("*" * 50)
            self.log.info(" NO ACTIVE NX CONNECTIONS FOUND ".center(50, "*"))
            self.log.info("*" * 50)
            return

        # 2. Build a fixed-width ASCII table for when there IS data
        # Find the maximum width needed for each column
        col_widths = [
            max(len(str(item)) for item in col) for col in zip(*list_of_lists)
        ]

        # Create a format string (e.g., "{:<20} | {:<15} | ...")
        format_str = " | ".join([f"{{:<{w}}}" for w in col_widths])

        # Create a separator line based on the total width
        separator_width = sum(col_widths) + 3 * (len(col_widths) - 1)
        separator = "-" * separator_width

        # Log the table line by line
        self.log.info(separator)
        for i, row in enumerate(list_of_lists):
            # Ensure all items are strings to prevent formatting errors
            str_row = [str(item) for item in row]
            self.log.info(format_str.format(*str_row))

            # Print a separator immediately after the header row
            if i == 0:
                self.log.info(separator)

        self.log.info(separator)

    def drive(self):
        try:
            if self.before():
                fedid = self.username
                pw = self.password
                nx_machines = self.nx_machines
                self.log.info("before set_running() in RemoteAccess")
                self.set_running()
                self.log.debug(
                    f"Trying to trigger collect remote No machine users on {self.class_name} module class"
                )
                nx_manager = Manage_NX_Connections(fedid, nx_machines, pw, self.log)
                self.log.debug(f"setting up nx_manager {nx_manager}")
                self.connections = nx_manager.get_list_of_sessions()
                self.log.info(f"remote NX connections:")
                self.log.info("")
                self.log_df(self.connections)
                self.log.info("")

                # Reported separately. Since the NoMachine upgrade the console
                # sessions on the beamline machines themselves - gdm, i04user -
                # appear in the same listing as real remote users, and mixing
                # them made the table read as though people were connected from
                # outside when they were not.
                self.local_connections = nx_manager.local_sessions
                if nx_manager.has_local_sessions():
                    self.log.info("local sessions on the beamline machines:")
                    self.log.info("")
                    self.log_df(self.local_connections)
                    self.log.info("")

                payload = {
                    "nx_connections": self.connections,
                    "local_sessions": self.local_connections,
                }
                if not nx_manager.has_remote_sessions():
                    payload["no_remote_message"] = "Nobody is connected remotely. " + (
                        f"{len(self.local_connections) - 1} local session(s) "
                        f"on the beamline machines are listed below."
                        if nx_manager.has_local_sessions()
                        else "There are no local sessions either."
                    )

                payload["table_title"] = self.ui.config.get("connections_table_title")
                payload["no_data_message"] = self.ui.config.get(
                    "no_connections_message"
                )

                self.store_report(payload)
                self.set_stopped()
            else:
                return False
            self.set_status_true()
            # Here some code just assess if this task ran successfully and set status to True/False
            status = True
            if status == False:
                self.set(f"{self.class_name}_status", status)
            return self.connections
        except Exception as e:
            self.log.critical(f"Failed with error {e}")
            self.set_status_false()
