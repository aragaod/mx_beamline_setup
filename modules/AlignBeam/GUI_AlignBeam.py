from UIs_py.rotation_axis import Ui_RemoteAccess_WZ as RA_UI_GUI
from PyQt5 import QtCore, QtGui, QtWidgets
import yaml as config_loader
import os
from base import BaseMGUI


class GUI(RA_UI_GUI, BaseMGUI):

    def retranslateUi(self, RemoteAccess_WZ):
        _translate = QtCore.QCoreApplication.translate
        RemoteAccess_WZ.setWindowTitle(
            _translate(self.config["WP1_Label_1_Title"], self.config["WP_Window_Title"])
        )

        # Force the text to align to the top-left to remove the huge gap
        self.WP1_Label_1.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)

        # Force word wrap so text like "reasonable" doesn't get cut off
        self.WP1_Label_1.setWordWrap(True)

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
    RotationAxis_WZ = QtWidgets.QWizard()
    ui = GUI()
    ui.read_config()
    ui.setupUi(RotationAxis_WZ)
    RotationAxis_WZ.show()
    # sys.exit(app.exec_())
