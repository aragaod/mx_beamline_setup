from base import MOD_Base
from PyQt5 import QtCore, QtGui, QtWidgets
from modules.InitialChecks.GUI_InitialChecks import GUI
import time


class InitialChecks(MOD_Base):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading {self.class_name}_MD module/instance")

        # IMPORTANT: a run method defined on the upper class MOD_Base is triggered by clicking this module button on the GUI. One can overwrite the run function if requeried
        # The run method contains a call to launch_GUI function. If launch GUI does not exists a place holder pass function is called.

    def launch_GUI(self):
        import sys

        self.InitialChecks_WZ = QtWidgets.QWizard()
        ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")
        ui.read_config()
        ui.setupUi(self.InitialChecks_WZ)

        # Connecting the Finish and Cancel buttons so that they trigger update of status. (set_status_true() set_status_false() are defined in Modules.py/MOD_Base
        self.InitialChecks_WZ.button(QtWidgets.QWizard.FinishButton).clicked.connect(
            self.set_status_true
        )
        self.InitialChecks_WZ.button(QtWidgets.QWizard.CancelButton).clicked.connect(
            self.set_status_false
        )
        self.InitialChecks_WZ.button(QtWidgets.QWizard.NextButton).clicked.connect(
            self.next
        )
        self.InitialChecks_WZ.button(QtWidgets.QWizard.BackButton).clicked.connect(
            self.back
        )

        # Handle pressing the top right X button
        self.InitialChecks_WZ.rejected.connect(self.reject)

        # Lock main window to prevent other tasks
        self.InitialChecks_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.InitialChecks_WZ.show()

        # import code
        # code.interact(local=locals())

    def next(self):
        self.log.debug(f"Next button pressed")

    def back(self):
        self.log.debug("Back button pressed")

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()
