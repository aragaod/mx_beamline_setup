from UIs_py.remote_access_checks import Ui_RemoteAccess_WZ as RA_UI_GUI
from PyQt5 import QtCore, QtGui, QtWidgets
import yaml as config_loader

import os
from base import BaseMGUI


class GUI(RA_UI_GUI, BaseMGUI):

    # The YAML is named after the file, not the module.
    config_basename = "GUI_RemoteAccess"

    def retranslateUi(self, RemoteAccess_WZ):
        _translate = QtCore.QCoreApplication.translate
        RemoteAccess_WZ.setWindowTitle(_translate("RemoteAccess_WZ", "Wizard"))
        self.WP1_Label_1.setText(
            _translate(
                self.config["WP1_Label_1_Title"], self.config["WP1_Label_1_Text"]
            )
        )
        self.WP2_Label_1.setText(
            _translate(
                self.config["WP2_Label_1_Title"], self.config["WP2_Label_1_Text"]
            )
        )


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    RemoteAccess_WZ = QtWidgets.QWizard()
    ui = GUI()
    ui.read_config()
    ui.setupUi(RemoteAccess_WZ)
    RemoteAccess_WZ.show()
    sys.exit(app.exec_())
