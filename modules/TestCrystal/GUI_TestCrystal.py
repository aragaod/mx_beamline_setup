from UIs_py.rotation_axis import Ui_RemoteAccess_WZ as RA_UI_GUI
from PyQt5 import QtCore, QtGui, QtWidgets
import yaml as config_loader
import os
from base import BaseMGUI


class GUI(RA_UI_GUI, BaseMGUI):

    def retranslateUi(self, TestCrystal_WZ):
        _translate = QtCore.QCoreApplication.translate
        TestCrystal_WZ.setWindowTitle(
            _translate("TestCrystal_WZ", "Test Crystal Module")
        )
        TestCrystal_WZ.setMinimumHeight(300)
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
    TestCrystal_WZ = QtWidgets.QWizard()
    ui = RA_UI_GUI()
    ui.read_config()
    ui.setupUi(TestCrystal_WZ)
    TestCrystal_WZ.show()
    # sys.exit(app.exec_())
