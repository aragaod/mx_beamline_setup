from base import MOD_Base
from PyQt5 import QtCore, QtGui, QtWidgets

from modules.BeamlineMessages.GUI_BeamlineMessages import GUI

from beamline import ID
from beamline import redis

import sys, json


class BeamlineMessages(MOD_Base):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading {self.class_name}_MD module/instance")

        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")

    def launch_GUI(self):
        import sys

        self.BeamlineMessages_W = QtWidgets.QWidget()

        self.ui.read_config()

        self.ui.rediskey = self.ui.config["rediskey"].format(BEAMLINE=ID)

        if redis.get(self.ui.rediskey):
            self.log.debug(
                f"Will use redis keys {self.ui.rediskey} to read and store messages"
            )
            self.ui.config = json.loads(redis.get(self.ui.rediskey))
        else:
            self.log.debug(
                f"Creating redis key {self.ui.rediskey} to read and store messages from YAML data"
            )
            redis.set(self.ui.rediskey, json.dumps(self.ui.config))

        self.ui.setupUi(self.BeamlineMessages_W)

        # Connecting the SaveClose, Cancel and Reread buttons so that they trigger respective tasks
        self.ui.SaveClose_PB.clicked.connect(self.save_and_close)
        self.ui.Cancel_PB.clicked.connect(self.cancel)
        self.ui.ReRead_PB.clicked.connect(self.reread)

        # Handle pressing the top right X button
        # self.InitialChecks_WZ.button.aboutToQuit.connect(self.set_status_false)
        # self.ui.rejected.connect(self.reject)

        # Lock main window to prevent other tasks
        self.BeamlineMessages_W.setWindowModality(QtCore.Qt.ApplicationModal)
        self.BeamlineMessages_W.show()

    def save_and_close(self):
        # Get UI_new_data
        self.ui.config["List_Widget_Data"] = self.ui.get_UI_data()

        self.log.debug(f'New data to be stored is {self.ui.config["List_Widget_Data"]}')

        # Save the data to redis
        redis.set(self.ui.rediskey, json.dumps(self.ui.config))
        self.log.debug(f"Stored data to redis key {self.ui.rediskey}")

        # Now we can update Main window checkbox and close the window
        self.set_status_true()
        self.BeamlineMessages_W.close()

    def cancel(self):
        # Now we can update Main window checkbox and close the window
        self.set_status_false()
        self.BeamlineMessages_W.close()

    def reread(self):
        # Re-read data
        self.ui.config = json.loads(redis.get(self.ui.rediskey))
        # Update widget
        self.ui.retranslateUi(self.BeamlineMessages_W)
        pass

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()
