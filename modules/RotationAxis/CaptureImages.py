from PyQt5 import QtGui
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication, QPushButton
from PyQt5.QtCore import *
from epics import PV
import numpy as np
import sys
import beamline
from PIL import Image
from PIL.ImageQt import ImageQt
import shutil

prefix = "BL04I-DI-OAV-01:ARR:"


class CaptureImages:

    # (TO finish, not critical)
    # Failed attempt (so far) to show an image (from epics or URL) into QT. Idea was to show the images that had just been taken.
    #
    def __init__(self, prefix):

        array = "ArrayData"
        size0 = "ArraySize0_RBV"
        size1 = "ArraySize1_RBV"
        size2 = "ArraySize2_RBV"

        array_pv = f"{prefix}{array}"
        size_pvs = [f"{prefix}{size0}", f"{prefix}{size1}", f"{prefix}{size2}"]

        self.array = PV(array_pv)
        self.sizes = [PV(size) for size in size_pvs]

        self.MainWindow = QWidget()

        self.MainWindow.btn = QPushButton("Button", self.MainWindow)
        self.MainWindow.btn.setToolTip("This is a <b>QPushButton</b> widget")
        self.MainWindow.btn.resize(self.MainWindow.btn.sizeHint())
        self.MainWindow.btn.move(50, 50)
        self.MainWindow.setGeometry(300, 300, 300, 200)

        self.MainWindow.btn.clicked.connect(self.save_image)

    def save_image(self):

        self.array_size = [size.get() for size in self.sizes]

        # self.data = np.array(self.data).reshape(self.array_size[0],self.array_size[1],self.array_size[2]).astype(np.int32)

        # print(self.data)

        # print(self.data.shape[0])
        # print(self.data.shape[1])
        # print(self.data.shape[2])

        url = f"http://{beamline.cameras.ROIs['xtal']['server']}{beamline.cameras.ROIs['xtal']['static'][0]}"

        image2 = self.get_image_from_url(url)
        image2 = self.get_image_from_epics(
            self.array, self.array_size[0], self.array_size[1], self.array_size[2]
        )

        # qimage = QtGui.QImage(self.data, self.data.shape[1],self.data.shape[2],QtGui.QImage.Format_RGB32)

        # qimage = QtGui.QImage(self.data,(1024,768),QtGui.QImage.Format_Indexed8)

        print("XX")
        pixmap = QtGui.QPixmap.fromImage(image2)

        print("XXX")
        # qimage = QtGui.QImage.loadFromData(self.data)
        # qimage = QtGui.QImage()
        # qimage.loadFromData(self.data)

        img = PrintImage(pixmap)
        print(img)
        self.MainWindow.setLayout(QVBoxLayout())

        self.MainWindow.layout().addWidget(img)
        print("YYYYY")

    def get_image_from_epics(self, epics_PV_instance, shape0, shape1, shape2):
        data = epics_PV_instance.get()
        self.data = np.array(data).reshape(shape0, shape1, shape2).astype(np.int32)
        qimage = QtGui.QImage(
            self.data, self.data.shape[2], self.data.shape[0], QtGui.QImage.Format_RGB32
        )
        return qimage

    def get_image_from_url(self, url, location="/var/tmp/", filename="image.jpg"):
        # import shutil
        import requests
        import io

        response = requests.get(url)
        i = Image.open(io.BytesIO(response.content))
        qimage = ImageQt(i)

        response = requests.get(url, stream=True)
        with open(f"{location}{filename}", "wb") as out_file:
            shutil.copyfileobj(response.raw, out_file)
        # del response
        return qimage


class PrintImage(QWidget):
    def __init__(self, pixmap, parent=None):
        QWidget.__init__(self, parent=parent)
        self.pixmap = pixmap

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)


if __name__ == "__main__":

    app = QApplication(sys.argv)
    panoramic = CaptureImages(prefix)
    panoramic.MainWindow.show()
    app.exec_()
