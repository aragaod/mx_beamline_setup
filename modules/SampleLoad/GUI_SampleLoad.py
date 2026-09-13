from UIs_py.rotation_axis import Ui_RemoteAccess_WZ as SL_UI_GUI
from base import BaseMGUI

from PyQt5 import QtCore, QtGui, QtWidgets
import yaml as config_loader
import os


class GUI(SL_UI_GUI, BaseMGUI):

    def retranslateUi(self, SampleLoad_WZ):
        _translate = QtCore.QCoreApplication.translate
        SampleLoad_WZ.setWindowTitle(
            _translate("RemoteAccess_WZ", "Sample Load Module")
        )
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
    SampleLoad_WZ = QtWidgets.QWizard()
    ui = GUI()
    ui.read_config()
    ui.setupUi(SampleLoad_WZ)
    RotationAxis_WZ.show()
    # sys.exit(app.exec_())
