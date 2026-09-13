from PyQt5 import QtWidgets

import paramiko as ssh
import getpass, socket
import pwd as unixpwd
import grp, os

from beamline import ID


class Login(QtWidgets.QDialog):
    def __init__(self, username, parent=None):
        super(Login, self).__init__(parent)
        self.setWindowTitle("Login: FEDID & pass")
        self.textName = QtWidgets.QLineEdit(username, parent=self)
        self.textPass = QtWidgets.QLineEdit(parent=self)
        self.textPass.setEchoMode(QtWidgets.QLineEdit.Password)
        self.buttonLogin = QtWidgets.QPushButton("Login", self)
        self.buttonLogin.clicked.connect(self.handleLogin)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.textName)
        layout.addWidget(self.textPass)
        layout.addWidget(self.buttonLogin)

        self.staffdetails = {}

        self.ID = ID

    def handleLogin(self):
        if self.check_auth(self.textName.text(), self.textPass.text()):
            self.accept()
        else:
            QtWidgets.QMessageBox.warning(self, "Error", self.error)

    def check_auth(self, user, pwd):
        machine = f"{self.ID}-ws001"
        ssh_con = ssh.SSHClient()
        ssh_con.set_missing_host_key_policy(ssh.AutoAddPolicy())
        try:
            self.error = "Bad user or password"
            ssh_con.connect(machine, username=user, password=pwd, look_for_keys=False)
            command = "ls -alrt /tmp"
            stdin, stdout, stderr = ssh_con.exec_command(command)
            self.staffdetails["username"] = user
            self.staffdetails["password"] = pwd
            if not self.check_groups(user):
                print(
                    f"The user logged in does not belong to the beamline staff or mx staff groups"
                )
                self.error = (
                    "This user does not belong to either mx or beamline staff groups."
                )
                return False
            self.get_name(user)
            return True
        except Exception as e:
            print(f"Maybe username or password wrong? error was {e}")
            return False

    def get_name(self, fedid):
        try:
            last_name = unixpwd.getpwnam(fedid)[4].split(",")[0].split()[0]
            self.staffdetails["last_name"] = last_name
            first_name = unixpwd.getpwnam(fedid)[4].split(",")[0].split()[1]
            self.staffdetails["first_name"] = first_name
            return True
        except Exception as e:
            print(f"Failed to get full name for {fedid} with error {e}")
            if self.staffdetails.get("last_name"):
                self.staffdetails["first_name"] = self.staffdetails["last_name"]
            else:
                self.staffdetails["first_name"] = "Jane"
                self.staffdetails["first_name"] = "Doe"
            return False

    def check_groups(self, fedid):
        # check belongs to mx_staff
        # check belongs to {ID}_staff
        to_check = ["mx_staff", f"{self.ID}_staff"]

        checks_passed = 0

        groups = [
            grp.getgrgid(g).gr_name
            for g in os.getgroups()
            if fedid in grp.getgrgid(g).gr_mem
        ]
        print(groups)
        print(fedid)
        for group in to_check:
            for item in groups:
                if item == group:
                    checks_passed += 1
                    break
        if checks_passed == len(to_check):
            return True
        else:
            return False


class Window(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super(Window, self).__init__(parent)
        # self.ui = Ui_MainWindow()
        # self.ui.setupUi(self)


if __name__ == "__main__":

    import sys

    app = QtWidgets.QApplication(sys.argv)
    login = Login()

    if login.exec_() == QtWidgets.QDialog.Accepted:
        window = Window()
        window.show()
        sys.exit(app.exec_())
