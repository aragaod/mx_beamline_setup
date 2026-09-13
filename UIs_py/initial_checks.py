# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'UIs/remote_access_checks.ui'
#
# Created by: PyQt5 UI code generator 5.12.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_RemoteAccess_WZ(object):
    def setupUi(self, RemoteAccess_WZ):
        RemoteAccess_WZ.setObjectName("RemoteAccess_WZ")
        RemoteAccess_WZ.setEnabled(True)
        RemoteAccess_WZ.resize(587, 480)
        font = QtGui.QFont()
        font.setPointSize(17)
        RemoteAccess_WZ.setFont(font)
        self.RA_Page_1 = QtWidgets.QWizardPage()
        self.RA_Page_1.setEnabled(True)
        self.RA_Page_1.setObjectName("RA_Page_1")
        self.WP1_Label_1 = QtWidgets.QLabel(self.RA_Page_1)
        self.WP1_Label_1.setGeometry(QtCore.QRect(10, 10, 511, 371))
        font = QtGui.QFont()
        font.setPointSize(13)
        self.WP1_Label_1.setFont(font)
        self.WP1_Label_1.setWordWrap(True)
        self.WP1_Label_1.setTextInteractionFlags(QtCore.Qt.LinksAccessibleByMouse|QtCore.Qt.TextSelectableByKeyboard|QtCore.Qt.TextSelectableByMouse)
        self.WP1_Label_1.setObjectName("WP1_Label_1")
        RemoteAccess_WZ.addPage(self.RA_Page_1)
        self.RA_Page_2 = QtWidgets.QWizardPage()
        self.RA_Page_2.setObjectName("RA_Page_2")
        self.WP2_Label_1 = QtWidgets.QLabel(self.RA_Page_2)
        self.WP2_Label_1.setGeometry(QtCore.QRect(20, 10, 511, 371))
        font = QtGui.QFont()
        font.setPointSize(11)
        self.WP2_Label_1.setFont(font)
        self.WP2_Label_1.setTextInteractionFlags(QtCore.Qt.LinksAccessibleByMouse|QtCore.Qt.TextSelectableByKeyboard|QtCore.Qt.TextSelectableByMouse)
        self.WP2_Label_1.setObjectName("WP2_Label_1")
        RemoteAccess_WZ.addPage(self.RA_Page_2)

        self.retranslateUi(RemoteAccess_WZ)
        QtCore.QMetaObject.connectSlotsByName(RemoteAccess_WZ)

    def retranslateUi(self, RemoteAccess_WZ):
        _translate = QtCore.QCoreApplication.translate
        RemoteAccess_WZ.setWindowTitle(_translate("RemoteAccess_WZ", "Wizard"))
        self.WP1_Label_1.setText(_translate("RemoteAccess_WZ", "If you have remote users today you should do the NX texts next. \n"
" If the users are remote you can press cancel now."))
        self.WP2_Label_1.setText(_translate("RemoteAccess_WZ", "Check if there are any old java processes from NX sessions that have not been properly closed and are not part of a current visit.\n"
"\n"
"Log in with your BL staff FedID, then open a shell and type:\n"
"> ssh -X yourFedID@i04-ws001\n"
"\n"
"To get a list of nx session use (you will be asked for your password):\n"
"> sudo /usr/NX/bin/nxserver --list \n"
"\n"
"To terminate an nx session use:\n"
"> sudo /usr/NX/bin/nxserver --terminate {number}\n"
"\n"
"To broadcast a message to all nx sessions:\n"
"> sudo /usr/NX/bin/nxserver --broadcast \"your message here\"\n"
"\n"
"Use \"finger\" to find which name is associated to a given FedID.\n"
"> finger {FedID}\n"
"\n"
"You press finished when done!"))




if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    RemoteAccess_WZ = QtWidgets.QWizard()
    ui = Ui_RemoteAccess_WZ()
    ui.setupUi(RemoteAccess_WZ)
    RemoteAccess_WZ.show()
    sys.exit(app.exec_())
