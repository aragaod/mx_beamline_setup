from UIs_py.initial_checks import Ui_RemoteAccess_WZ as IC_UI_GUI
from PyQt5 import QtCore, QtGui, QtWidgets
import yaml as config_loader
import os
from base import BaseMGUI


class GUI(IC_UI_GUI, BaseMGUI):

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
    ui = RA_GUI()
    ui.read_config()
    ui.setupUi(RemoteAccess_WZ)
    RemoteAccess_WZ.show()
    # sys.exit(app.exec_())
