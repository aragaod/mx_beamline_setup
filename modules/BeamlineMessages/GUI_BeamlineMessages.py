from UIs_py.BeamlineMessages_list import Ui_BeamlineMessages_W as BM_UI_GUI
from PyQt5 import QtCore, QtGui, QtWidgets
import yaml as config_loader
import os
from base import BaseMGUI


class GUI(BM_UI_GUI, BaseMGUI):

    def retranslateUi(self, BeamlineMessages_W):
        _translate = QtCore.QCoreApplication.translate
        BeamlineMessages_W.setWindowTitle(
            _translate(self.config["Widget_Name"], self.config["Widget_Title"])
        )
        __sortingEnabled = self.MessagesList_LW.isSortingEnabled()
        self.MessagesList_LW.setSortingEnabled(False)
        item = self.MessagesList_LW.item(0)
        item.setText(
            _translate(self.config["Widget_Name"], self.config["List_Widget_Data"][0])
        )
        item = self.MessagesList_LW.item(1)
        item.setText(
            _translate(self.config["Widget_Name"], self.config["List_Widget_Data"][1])
        )
        item = self.MessagesList_LW.item(2)
        item.setText(
            _translate(self.config["Widget_Name"], self.config["List_Widget_Data"][2])
        )
        item = self.MessagesList_LW.item(3)
        item.setText(
            _translate(self.config["Widget_Name"], self.config["List_Widget_Data"][3])
        )
        item = self.MessagesList_LW.item(4)
        item.setText(
            _translate(self.config["Widget_Name"], self.config["List_Widget_Data"][4])
        )
        self.MessagesList_LW.setSortingEnabled(__sortingEnabled)
        self.SaveClose_PB.setText(
            _translate(self.config["Widget_Name"], self.config["Push_Button_SaveClose"])
        )
        self.Cancel_PB.setText(
            _translate(self.config["Widget_Name"], self.config["Push_Button_Cancel"])
        )
        self.ReRead_PB.setText(
            _translate(self.config["Widget_Name"], self.config["Push_Button_ReRead"])
        )
        self.Title_L.setText(
            _translate(self.config["Widget_Name"], self.config["List_Widget_Title"])
        )

    def get_UI_data(self):
        payload = []
        # print(f'XXXXXXX {self.MessagesList_LW.count()}')
        for n in range(self.MessagesList_LW.count()):
            # print(n)
            item = self.MessagesList_LW.item(n)
            payload.append(item.text())
        return payload


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    BeamlineMessages_W = QtWidgets.QWidget()
    ui = Ui_BeamlineMessages_W()
    ui.setupUi(BeamlineMessages_W)
    BeamlineMessages_W.show()
    sys.exit(app.exec_())
