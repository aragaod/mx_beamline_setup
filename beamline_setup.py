#!/bin/env python3

# QT5 imports
from PyQt5 import QtWidgets, QtCore

# App imports
from base import APP_GUI, APP_Base
from base import login
from datetime import datetime


class BL_MainWindow(APP_GUI, APP_Base):
    def __init__(self, window, staffdetails, configuration_file):
        """
        Beamline Setup Main Class
        This the the main class that can be edited by the different beamlines and synchrotrons to overide upstream methods
        """

        if configuration_file == "default":
            config = "default"
        else:
            config = configuration_file

        # APP_Base loads configuration and sets up logging
        APP_Base.__init__(self, yaml_file=config)

        # APP_GUI prepars QT5 GUI and populates list of available objects. Needs to know information about modules (from APP_base)
        # So that that is knows what modules to load
        APP_GUI.__init__(self, window)

        # Auth
        self.staffdetails = staffdetails
        self.username = staffdetails["username"]
        self.password = staffdetails["password"]

        self.log.info(
            f'Hello {self.staffdetails["first_name"]}, good to see you. Good luck with the setup'
        )

        # Note who started a setup and when, for the overtime report (F2). Staff
        # claiming weekend overtime otherwise have to remember which days they
        # were Local Contact.
        self.record_oncall(
            "session_started",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            username=self.username,
        )

        self.log.info(
            f"Ready to start BeamlineSetup quality control and checklist for {self.ID}"
        )
        self.add_update_widget_to_module_instances()

    def delete_redis_update_UI(self):
        self.delete_redis_key()
        self.update_all_widgets()

    def update_widget(self, task, status=2, value="current"):
        """
        Widget types suppported. If you add more please fix me:
            - DateEdit (DE)
            - CheckBox (CB)
            - Close APP (CLOSE)
            - Do nothing (UNK)
        the widgets are defined in the __init_ function for each module in the modules directory

        e.g
        ui.update_widget('InitialChecks',status=2) - CB full ticked
        ui.update_widget('InitialChecks',status=1) - CB half ticked
        ui.update_widget('InitialChecks',status=0) - CB unticked

        """
        widget_type = self.MD[task].widget2update
        if widget_type == "UNK":
            self.log.debug(
                "This module is configured not to update any widget. All done"
            )
        elif widget_type == "DE" or widget_type == "CB" or widget_type == "CLOSE":
            # `value` has to be passed on. It was accepted here and then dropped,
            # so _update_widget_ always fell back to its default of "current" and
            # stamped the last-run time as now.
            #
            # That mattered because pressing a button half-ticks the checkbox
            # before the module runs, with value="db" meaning "keep whatever
            # timestamp is already there". With the argument dropped, pressing the
            # button recorded the module as having just run - so a module that
            # then failed still looked done on the next launch, for as long as its
            # criteria2expire window lasted.
            self._update_widget_(task, status, widget_type, value)

            if status == 0:
                # Overwrite last run date stamp in redis
                self.log.debug(
                    f"Overwriting datastamp for {task} of widget {widget_type}"
                )
                self.set(
                    f"{task}_{widget_type}_lastrun",
                    QtCore.QDateTime.fromSecsSinceEpoch(1553504400),
                )
        else:
            self.log.debug(f"don't know this widget yet {widget_type} please extend me")

    def add_update_widget_to_module_instances(self):
        # THis will allow the different beamline setup modules to update the CB by accessing this function if they require.
        for modu in self.MD:
            self.MD[modu].update_widget = self.update_widget
            self.log.debug(
                f"setting module {modu} new function update_widget to {self.update_widget} #####"
            )
            self.MD[modu].password = self.password
            self.MD[modu].username = self.username

    def update_all_widgets(self):
        for widget_type in ["DE", "CB"]:
            # getattr will convert to self.DE or self.CB
            for obj in getattr(self, widget_type):
                lastrun = self.get(f"{obj}_{widget_type}_lastrun")
                if not lastrun:
                    self.log.debug(
                        "redis hash key for storing time for last run is empty. Creating a new one"
                    )
                    self.set(
                        f"{obj}_{widget_type}_lastrun",
                        QtCore.QDateTime.fromSecsSinceEpoch(1553504400),
                    )  # default to EPOC for when DGA started working at Diamond :$
                    lastrun = self.get(f"{obj}_{widget_type}_lastrun")
                self.log.debug(
                    f"{obj}: Going to update {obj} for widget {widget_type} with new time"
                )

                # CB and DE Widgets have a criteria for how long before they need to be updated (see config yaml file)
                if widget_type == "CB" or widget_type == "DE":
                    status = self.check_criteria4CBs(obj, widget_type, lastrun)
                else:
                    status = -1
                self._update_widget_(obj, status, widget_type, lastrun)


if __name__ == "__main__":
    import sys
    import os

    username = os.environ.get("USER")
    BLrelease = os.environ.get("BLrelease")
    print(f"BLrelease set to: {BLrelease}")
    app = QtWidgets.QApplication(sys.argv)
    auth = login.Login(username)
    if auth.exec_() == QtWidgets.QDialog.Accepted:
        MainWindow = QtWidgets.QFrame()
        # ui = BL_MainWindow(MainWindow,auth.staffdetails,'default')
        # print(auth.staffdetails)
        if BLrelease == "production":
            ui = BL_MainWindow(MainWindow, auth.staffdetails, "configure_blsetup.yaml")
        elif BLrelease == "development":
            ui = BL_MainWindow(
                MainWindow, auth.staffdetails, "configure_blsetup_devel.yaml"
            )
        else:
            print("I don't know which release to load: production or development")
            sys.exit()
        ui.username = auth.textName.text()
        # ui.password = auth.textPass.text()
        # print(ui.username)
        # ui.setupUi(MainWindow)
        # ui.prepare()
        ui.MainWindow.show()
        sys.exit(app.exec_())

        # ui.log.info('Launchers with arguments')
        # ui.log.info(f'{sys.argv}')

        # from pprint import pprint
        # pprint(ui.get_all())
        # import code
        # code.interact(local = locals())
