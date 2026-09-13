# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'UIs/BeamlineMessages_list.ui'
#
# Created by: PyQt5 UI code generator 5.12.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_BeamlineMessages_W(object):
    def setupUi(self, BeamlineMessages_W):
        BeamlineMessages_W.setObjectName("BeamlineMessages_W")
        BeamlineMessages_W.resize(702, 209)
        BeamlineMessages_W.setStyleSheet("QWidget {background-color:white}\n"
"QPushButton { background-color: white }")
        self.MessagesList_LW = QtWidgets.QListWidget(BeamlineMessages_W)
        self.MessagesList_LW.setGeometry(QtCore.QRect(10, 40, 681, 111))
        self.MessagesList_LW.setObjectName("MessagesList_LW")
        item = QtWidgets.QListWidgetItem()
        item.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEditable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled)
        self.MessagesList_LW.addItem(item)
        item = QtWidgets.QListWidgetItem()
        item.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEditable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled)
        self.MessagesList_LW.addItem(item)
        item = QtWidgets.QListWidgetItem()
        item.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEditable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled)
        self.MessagesList_LW.addItem(item)
        item = QtWidgets.QListWidgetItem()
        item.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEditable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled)
        self.MessagesList_LW.addItem(item)
        item = QtWidgets.QListWidgetItem()
        item.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEditable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled)
        self.MessagesList_LW.addItem(item)
        self.SaveClose_PB = QtWidgets.QPushButton(BeamlineMessages_W)
        self.SaveClose_PB.setGeometry(QtCore.QRect(510, 160, 145, 28))
        self.SaveClose_PB.setAutoFillBackground(False)
        self.SaveClose_PB.setAutoDefault(False)
        self.SaveClose_PB.setDefault(True)
        self.SaveClose_PB.setFlat(False)
        self.SaveClose_PB.setObjectName("SaveClose_PB")
        self.Cancel_PB = QtWidgets.QPushButton(BeamlineMessages_W)
        self.Cancel_PB.setGeometry(QtCore.QRect(350, 160, 145, 28))
        self.Cancel_PB.setAutoFillBackground(False)
        self.Cancel_PB.setAutoDefault(False)
        self.Cancel_PB.setDefault(True)
        self.Cancel_PB.setFlat(False)
        self.Cancel_PB.setObjectName("Cancel_PB")
        self.ReRead_PB = QtWidgets.QPushButton(BeamlineMessages_W)
        self.ReRead_PB.setGeometry(QtCore.QRect(190, 160, 145, 28))
        self.ReRead_PB.setAutoFillBackground(False)
        self.ReRead_PB.setAutoDefault(False)
        self.ReRead_PB.setDefault(True)
        self.ReRead_PB.setFlat(False)
        self.ReRead_PB.setObjectName("ReRead_PB")
        self.Title_L = QtWidgets.QLabel(BeamlineMessages_W)
        self.Title_L.setGeometry(QtCore.QRect(40, 0, 631, 31))
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(15)
        self.Title_L.setFont(font)
        self.Title_L.setObjectName("Title_L")

        self.retranslateUi(BeamlineMessages_W)
        QtCore.QMetaObject.connectSlotsByName(BeamlineMessages_W)

    def retranslateUi(self, BeamlineMessages_W):
        _translate = QtCore.QCoreApplication.translate
        BeamlineMessages_W.setWindowTitle(_translate("BeamlineMessages_W", "Messages from fellow staff"))
        __sortingEnabled = self.MessagesList_LW.isSortingEnabled()
        self.MessagesList_LW.setSortingEnabled(False)
        item = self.MessagesList_LW.item(0)
        item.setText(_translate("BeamlineMessages_W", "Test1"))
        item = self.MessagesList_LW.item(1)
        item.setText(_translate("BeamlineMessages_W", "Test2"))
        item = self.MessagesList_LW.item(2)
        item.setText(_translate("BeamlineMessages_W", "Test3"))
        item = self.MessagesList_LW.item(3)
        item.setText(_translate("BeamlineMessages_W", "Test4"))
        item = self.MessagesList_LW.item(4)
        item.setText(_translate("BeamlineMessages_W", "Test5"))
        self.MessagesList_LW.setSortingEnabled(__sortingEnabled)
        self.SaveClose_PB.setText(_translate("BeamlineMessages_W", "Save and Close"))
        self.Cancel_PB.setText(_translate("BeamlineMessages_W", "Cancel"))
        self.ReRead_PB.setText(_translate("BeamlineMessages_W", "Re-Read"))
        self.Title_L.setText(_translate("BeamlineMessages_W", "Messages from fellow staff members about previous setups or issues"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    BeamlineMessages_W = QtWidgets.QWidget()
    ui = Ui_BeamlineMessages_W()
    ui.setupUi(BeamlineMessages_W)
    BeamlineMessages_W.show()
    sys.exit(app.exec_())
