"""
documentation: https://doc.qt.io/qtforpython/index.html
"""
from PySide2 import QtCore, QtGui, QtWidgets
from shiboken2 import wrapInstance
from maya import OpenMayaUI as omui
import maya.api.OpenMaya as OpenMaya
import pymel.core as pm
from functools import partial

import logging
logging.basicConfig()
logger = logging.getLogger('Picker UI:')
logger.setLevel(logging.INFO)

class dragButton(QtWidgets.QPushButton):
    def __init__(self, title, parent):
        super(dragButton, self).__init__(title, parent)
        self.setAcceptDrops(True)

    def mouseMoveEvent(self, e):
        # only drag and drop with right mouse button
        # documentation: QMouseEvents: https://doc-snapshots.qt.io/qtforpython/PySide2/QtGui/QMouseEvent.html#PySide2.QtGui.QMouseEvent
        if e.buttons() != QtCore.Qt.RightButton:
            return
        # documentation: https://doc-snapshots.qt.io/qtforpython/PySide2/QtCore/QMimeData.html?highlight=qmimedata
        # define information than can be stored in the clipboard, and transfered via drag and drop
        mimeData = QtCore.QMimeData()

        # documentation: https://doc-snapshots.qt.io/qtforpython/PySide2/QtGui/QDrag.html#PySide2.QtGui.QDrag
        drag = QtGui.QDrag(self)
        drag.setMimeData(mimeData)
        # documentation: https://doc-snapshots.qt.io/qtforpython/PySide2/QtCore/QRect.html#PySide2.QtCore.QRect
        # topLeft() returns the position of the topLeft corner
        drag.setHotSpot(e.globalPos() - self.rect().topLeft())

        dropAction = drag.start(QtCore.Qt.MoveAction)

    # left click normal event
    def mousePressEvent(self, e):
        QtWidgets.QPushButton.mousePressEvent(self, e)  # prepare inherit class too
        # only on left button clicks
        if e.button() == QtCore.Qt.LeftButton:
            pass

    def dropEvent(self, e):
        # unpack dropped data, and handle it in way that is suitable
        # review, dropEvent
        position = e.pos()
        self.move(position)

        e.setDropAction(QtCore.Qt.MoveAction)
        e.accept()

class PickerUI(QtWidgets.QWidget):
    """
    """
    idCallBack = []
    def __init__(self, dock=True):
        if dock:
            parent = getDock()
        else:
            deleteDock()
            try:
                pm.deleteUI('PickerUI')
            except:
                logger.debug('no previous ui detected')

            # top level window
            parent = QtWidgets.QDialog(parent=getMayaWindow())
            parent.setObjectName('PickerUI')
            parent.setWindowTitle('Picker UI')
            # parent.closeEvent(lambda: logger.debug('clossing'))
            # Review: do not work well if not dockable
            # add a layout
            dlgLayout = QtWidgets.QVBoxLayout(parent)
            # dlgLayout.addWidget(self)

        parent.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        super(PickerUI, self).__init__(parent=parent)
        self.parent().layout().addWidget(self)  # add widget finding previously the parent

        # delete on close
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        # when parent is destroyed, child launch close method. we connect the signals.
        parent.destroyed.connect(self.close)

        self.buildUI()
        self.__refresh()

        # callBack
        #self.idCallBack.append(OpenMaya.MEventMessage.addEventCallback('SceneOpened', self. __refresh))
        #self.idCallBack.append(OpenMaya.MEventMessage.addEventCallback('NameChanged', self. __refresh))

    def buildUI(self):
        # layout
        generalGrid = QtWidgets.QGridLayout(self)

        self.buttonsArea = QtWidgets.QWidget()
        #buttonsArea.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self.setAcceptDrops(True)  # accept drag and drop, necessary for move buttons

        # container
        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setAlignment(QtCore.Qt.AlignJustify)
        # Apply to scrollWidget
        scrollArea.setWidget(self.buttonsArea)
        generalGrid.addWidget(scrollArea, 0, 0)

        # buttons
        self.button = dragButton('Button', self.buttonsArea)
        self.button.move(500, 65)
        self.button.setAutoFillBackground(True)
        #button.setStyleSheet('background-color : red')
        #palette = QtGui.QPalette('button')
        palette = self.button.palette()
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor(155, 0, 0, 255))
        self.button.setPalette(palette)

        otherButton = dragButton('OtherButton', self.buttonsArea)
        otherButton.move(200, 30)

    def add(self):
        """
        add attributes and refresh the container
        """
        pass

    def __refresh(self, *args):
        """
        Refresh container, for add and remove options, or change attributes
        """
        pass

    ## drag events ##
    def dragEnterEvent(self, e):
        # review, dragEnterEvent
        # types of data widget accepts, p.e plane text or widgets
        position = e.pos()
        e.accept()

    def dropEvent(self, e):
        # unpack dropped data, and handle it in way that is suitable
        # review, dropEvent
        position = e.pos()
        #self.draggButton.move(position)

        e.setDropAction(QtCore.Qt.MoveAction)
        e.accept()


    # when close event, delete callbacks
    def closeEvent(self, event):
        for i, val in enumerate(self.idCallBack):
            # Event callback
            try:
                OpenMaya.MMessage.removeCallback(val)
                logger.debug('MMessage Callback removed: %s' % i)
            except:
                pass


def getPathFunc(defaultPath):
    pathWin = QtWidgets.QFileDialog.getExistingDirectory(parent=getMayaWindow(), caption='FBX exporter browser', dir=defaultPath)
    if not pathWin:
        return defaultPath
    return pathWin

def getDock(name='PickerUIDock'):
    deleteDock(name)

    # Creates and manages the widget used to host windows in a layout
    # which enables docking and stacking windows together
    ctrl = pm.workspaceControl(name, dockToMainWindow=('right', 1), label='Picker UI')
    # we need the QT version, MQtUtil_findControl return the qt widget of the named maya control
    qtCtrl = omui.MQtUtil_findControl(ctrl)
    # translate to something python understand
    ptr = wrapInstance(long(qtCtrl), QtWidgets.QWidget)

    return ptr

def deleteDock(name = 'PickerUIDock'):
    if pm.workspaceControl(name, query=True, exists=True):
        pm.deleteUI(name)

def getMayaWindow():
    #get maya main window
    win = omui.MQtUtil_mainWindow()
    ptr = wrapInstance(long(win), QtWidgets.QMainWindow)

    return ptr

"""
from FbxExporter import FbxExporterUI
from FbxExporter import FbxExporter
reload(FbxExporter)
reload(FbxExporterUI)
ui = FbxExporterUI.FbxExporterUI(True)
"""