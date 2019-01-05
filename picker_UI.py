"""
documentation: https://doc.qt.io/qtforpython/index.html
"""
from PySide2 import QtCore, QtGui, QtWidgets
from shiboken2 import wrapInstance
from maya import OpenMayaUI
import maya.api.OpenMaya as OpenMaya
import pymel.core as pm
import maya.cmds as cmds
import math
from functools import partial

import logging
logging.basicConfig()
logger = logging.getLogger('Picker UI:')
logger.setLevel(logging.DEBUG)

class dragButton(QtWidgets.QPushButton):
    def __init__(self, title, parent):
        super(dragButton, self).__init__(title, parent)
        self.setAcceptDrops(True)

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton:
            # adjust offset from clicked point to origin of widget
            currPos = self.mapToGlobal(self.pos())
            globalPos = event.globalPos()
            diff = globalPos - self.__mouseMovePos
            newPos = self.mapFromGlobal(currPos + diff)
            self.move(newPos)

            self.__mouseMovePos = globalPos

        super(dragButton, self).mouseMoveEvent(event)

    # left click normal event
    def mousePressEvent(self, event):
        self.__mousePressPos = None
        self.__mouseMovePos = None
        if event.button() == QtCore.Qt.LeftButton:
            self.__mousePressPos = event.globalPos()
            self.__mouseMovePos = event.globalPos()

        super(dragButton, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.__mousePressPos is not None:
            moved = event.globalPos() - self.__mousePressPos
            if moved.manhattanLength() > 3:
                event.ignore()
                self.setDown(False)
                return

        super(dragButton, self).mouseReleaseEvent(event)

class PickerUI(QtWidgets.QWidget):
    """
    """
    controllerDict = {u'clavicle_right_ctr': [[0.3297690590983669, 0.20423970384453974], [0.07774357814250528, 0.021231880014487132], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'arm_right_foreArm_fk_ctr': [[0.23455582747671, 0.37812064322863553], [0.04583333336708854, 0.12438271382254484], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'head_ctr': [[0.4375, 0.008304217869643749], [0.125, 0.125], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'foot_left_toeC1_fk_ctr': [[0.5749100642819359, 0.8872156048586467], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'fingerA3_left_ctr': [[0.6881842920481328, 0.5603664027375498], [0.017251504813196778, 0.01848185127445771], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'spine_end_ctr': [[0.4208333326747453, 0.20405682188033367], [0.15833333465050922, 0.05274491556539718], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'arm_right_upperArm_fk_ctr': [[0.23455582747671, 0.20397780381957217], [0.04583333336708854, 0.12438749997406447], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'fingerD3_right_ctr': [[0.24020497259881077, 0.6254713355971852], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'foot_right_toeE3_fk_ctr': [[0.37481854511138885, 0.9243779098078977], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'hips_ctr': [[0.43749999999999994, 0.4351851878042979], [0.125, 0.039918563883214464], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'fingerE1_right_ctr': [[0.22422139320030735, 0.5883090306479342], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'twist2_leg_right_upperLeg_ctr': [[0.34000261742986965, 0.6009370802698629], [0.04583333336708847, 0.022469139701828993], (0.027883177623152733, 0.18752333521842957, 0.5467289686203003)], u'fingerB1_right_ctr': [[0.2743930642501979, 0.5883090306479342], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'spine_2_fk_ctr': [[0.43606053184855603, 0.3685420313413537], [0.1278789363028879, 0.01910869193727575], (0.6214953064918518, 0.03162272647023201, 0.03162272647023201)], u'fingerA3_right_ctr': [[0.2945642031386705, 0.5603664027375498], [0.017251504813196705, 0.01848185127445771], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'twist1_leg_right_lowerLeg_ctr': [[0.34000261742986965, 0.712588008713363], [0.04583333336708847, 0.02246913970182914], (0.027883177623152733, 0.18752333521842957, 0.5467289686203003)], u'fingerC2_right_ctr': [[0.25704205589418794, 0.6066192975249884], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'arm_right_wire_ctr': [[0.23062685323419507, 0.3406003594667248], [0.05138889342234654, 0.025867229487245364], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'leg_left_lowerLeg_fk_ctr': [[0.5576013515348602, 0.6697826430406749], [0.04583333336708847, 0.14444444384189983], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185)], u'twist1_leg_left_lowerLeg_ctr': [[0.6141640492030419, 0.7125880087133631], [0.04583333336708847, 0.02246913970182914], (0.07124946266412735, 0.44392523169517517, 0.022640159353613853)], u'foot_right_toeB3_fk_ctr': [[0.42783211213452077, 0.9243779098078977], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'main_ctr': [[0.2294399812168683, 0.974684399135699], [0.5411200375662631, 0.02123188001448728], (0.03407939895987511, 0.5218848586082458, 0.6682242751121521)], u'fingerA2_right_ctr': [[0.2945642031386705, 0.5388182695041794], [0.017251504813196705, 0.01848185127445771], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'foot_right_toeE2_fk_ctr': [[0.37481854511138885, 0.905525871735701], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'fingerE1_left_ctr': [[0.761619636022305, 0.5883090306479342], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'twist2_leg_right_lowerLeg_ctr': [[0.34000261742986965, 0.7684134729351131], [0.04583333336708847, 0.02246913970182914], (0.027883177623152733, 0.18752333521842957, 0.5467289686203003)], u'foot_left_toeA1_fk_ctr': [[0.5369412300543542, 0.88714808746317], [0.017665656877702496, 0.013524567036292604], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'fingerB1_left_ctr': [[0.7114479649724145, 0.5883090306479342], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'foot_right_footToes_ik_ctr': [[0.4063538405190939, 0.9458093364084806], [0.02130544984453116, 0.021305449844531015], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'fingerC1_left_ctr': [[0.7287989733284244, 0.5883090306479342], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'fingerD3_left_ctr': [[0.7456360566238015, 0.6254713355971852], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'foot_right_toeB2_fk_ctr': [[0.42783211213452077, 0.905525871735701], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'fingerE2_right_ctr': [[0.22422139320030735, 0.6066192975249884], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'fingerB2_left_ctr': [[0.7114479649724145, 0.6066192975249884], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'foot_right_footTiltIn_ik_ctr': [[0.47060969758762655, 0.8779464950184036], [0.02130544984453116, 0.021305449844531015], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'foot_right_foot_fk_ctr': [[0.3885705021947948, 0.8228203883215662], [0.0625115363627587, 0.05955112947242499], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'spine_3_fk_ctr': [[0.43606053184855603, 0.30285010130840073], [0.1278789363028879, 0.019108691937275674], (0.6214953064918518, 0.03162272647023201, 0.03162272647023201)], u'foot_left_toeC2_fk_ctr': [[0.5749100642819359, 0.905525871735701], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_left_toeA2_fk_ctr': [[0.5369412300543542, 0.9053548110437362], [0.017665656877702496, 0.013524567036292604], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_right_toeA1_fk_ctr': [[0.4453931130679433, 0.8871480874631702], [0.017665656877702496, 0.013524567036292604], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_right_toeD3_fk_ctr': [[0.39260460590741514, 0.9243779098078977], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_left_footTiltOut_ik_ctr': [[0.6344967912087889, 0.8779464950184034], [0.02130544984453116, 0.021305449844531015], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'fingerA1_left_ctr': [[0.6881842920481328, 0.5177923708049647], [0.017251504813196778, 0.01848185127445771], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'leg_right_lowerLeg_fk_ctr': [[0.3965653150980513, 0.6697826430406747], [0.04583333336708847, 0.14444444384189983], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'foot_left_footTiltIn_ik_ctr': [[0.5080848525678423, 0.8779464950184034], [0.02130544984453116, 0.021305449844531015], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'fingerC3_left_ctr': [[0.7287989733284244, 0.6254713355971852], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'arm_left_upperArm_fk_ctr': [[0.7196108391562014, 0.20397780381957217], [0.04583333336708861, 0.12438749997406447], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'foot_right_footTiltOut_ik_ctr': [[0.34419775894668, 0.8779464950184034], [0.02130544984453116, 0.021305449844531015], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'foot_left_foot_fk_ctr': [[0.5489179614424465, 0.8228203883215662], [0.0625115363627587, 0.05955112947242499], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_left_toeE2_fk_ctr': [[0.6101229501603475, 0.905525871735701], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'clavicle_left_ctr': [[0.5924873627591278, 0.20423970384453974], [0.07774357814250532, 0.021231880014487132], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'foot_right_toeC1_fk_ctr': [[0.4100314309898003, 0.8872156048586467], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'fingerC3_right_ctr': [[0.25704205589418794, 0.6254713355971852], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'fingerD1_right_ctr': [[0.24020497259881077, 0.5883090306479342], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'foot_right_toeB1_fk_ctr': [[0.42783211213452077, 0.8872156048586467], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'leg_right_upperLeg_fk_ctr': [[0.3965653150980513, 0.5176443886588098], [0.04583333336708847, 0.14444444384189983], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'fingerB3_left_ctr': [[0.7114479649724145, 0.6254713355971852], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'foot_left_toeB1_fk_ctr': [[0.5571093831372155, 0.8872156048586467], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_right_toeD1_fk_ctr': [[0.39260460590741514, 0.8872156048586467], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_right_footHeel_ik_ctr': [[0.4551387124142008, 0.7935259158871185], [0.02130544984453116, 0.021320713861436264], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'clavicle_right_swing_fk_ctr': [[0.2947928274670864, 0.16279256600939332], [0.02099999999999998, 0.06199999999999998], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'arm_left_foreArm_fk_ctr': [[0.7196108391562014, 0.37812064322863553], [0.04583333336708861, 0.12438271382254484], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'foot_left_toeD2_fk_ctr': [[0.5923368893643212, 0.905525871735701], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_right_toeE1_fk_ctr': [[0.37481854511138885, 0.8872156048586467], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'fingerE3_left_ctr': [[0.761619636022305, 0.6254713355971852], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'spine_spine1_1_ik_ctr': [[0.43749999999999994, 0.39801472046163444], [0.125, 0.025867229487245364], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'fingerA1_right_ctr': [[0.2945642031386705, 0.5177923708049647], [0.017251504813196705, 0.01848185127445771], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'fingerC1_right_ctr': [[0.25704205589418794, 0.5883090306479342], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'ik_arm_left_pole_ctr': [[0.8042865907555324, 0.3365941392271075], [0.03749999999999994, 0.03749999999999994], (0.6214953064918518, 0.03162272647023201, 0.03162272647023201)], u'fingerD1_left_ctr': [[0.7456360566238015, 0.5883090306479342], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'fingerA2_left_ctr': [[0.6881842920481328, 0.5388182695041794], [0.017251504813196778, 0.01848185127445771], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'foot_right_toeC2_fk_ctr': [[0.4100314309898003, 0.905525871735701], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_left_toeC3_fk_ctr': [[0.5749100642819359, 0.9243779098078976], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'fingerB2_right_ctr': [[0.2743930642501979, 0.6066192975249884], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'spine_spine3_1_ik_ctr': [[0.43749999999999994, 0.2673313787246238], [0.125, 0.02586722948724544], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'neckHead_neck_2_fk_ctr': [[0.46112821092874734, 0.1419994460070075], [0.07774357814250532, 0.02123188001448717], (0.6214953064918518, 0.03162272647023201, 0.03162272647023201)], u'foot_left_toeB2_fk_ctr': [[0.5571093831372155, 0.905525871735701], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'twist1_leg_right_upperLeg_ctr': [[0.34000261742986965, 0.545111616048113], [0.04583333336708847, 0.022469139701828993], (0.027883177623152733, 0.18752333521842957, 0.5467289686203003)], u'clavicle_left_swing_fk_ctr': [[0.6841666666666667, 0.16279256600939332], [0.020999999999999908, 0.06199999999999998], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'foot_right_toeD2_fk_ctr': [[0.39260460590741514, 0.905525871735701], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_left_toeE3_fk_ctr': [[0.6101229501603475, 0.9243779098078976], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_right_toeC3_fk_ctr': [[0.4100314309898003, 0.9243779098078977], [0.015058504728263719, 0.01594009898076454], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'foot_right_toeA2_fk_ctr': [[0.4453931130679433, 0.9053548110437362], [0.017665656877702496, 0.013524567036292604], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_leg_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'twist3_leg_left_upperLeg_ctr': [[0.6141640492030419, 0.6567625444916131], [0.04583333336708847, 0.022469139701829066], (0.07124946266412735, 0.44392523169517517, 0.022640159353613853)], u'foot_left_toeB3_fk_ctr': [[0.5571093831372155, 0.9243779098078976], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'spine_spine2_1_ik_ctr': [[0.43749999999999994, 0.3327790729446756], [0.125, 0.025867229487245402], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'fingerD2_right_ctr': [[0.24020497259881077, 0.6066192975249884], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'foot_left_footHeel_ik_ctr': [[0.523555837741268, 0.7935259158871184], [0.02130544984453116, 0.021320713861436264], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'twist1_leg_left_upperLeg_ctr': [[0.6141640492030419, 0.545111616048113], [0.04583333336708847, 0.022469139701828993], (0.07124946266412735, 0.44392523169517517, 0.022640159353613853)], u'leg_left_upperLeg_fk_ctr': [[0.5576013515348602, 0.5176443886588098], [0.04583333336708847, 0.14444444384189983], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185)], u'foot_left_toeE1_fk_ctr': [[0.6101229501603475, 0.8872156048586467], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'fingerB3_right_ctr': [[0.2743930642501979, 0.6254713355971852], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'foot_left_footToes_ik_ctr': [[0.572340709636375, 0.9458093364084804], [0.02130544984453116, 0.021305449844531015], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'twist2_leg_left_upperLeg_ctr': [[0.6141640492030419, 0.6009370802698629], [0.04583333336708847, 0.022469139701828993], (0.07124946266412735, 0.44392523169517517, 0.022640159353613853)], u'foot_left_toeD1_fk_ctr': [[0.5923368893643212, 0.8872156048586467], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'twist2_leg_left_lowerLeg_ctr': [[0.6141640492030419, 0.7684134729351132], [0.04583333336708847, 0.02246913970182914], (0.07124946266412735, 0.44392523169517517, 0.022640159353613853)], u'arm_left_wire_ctr': [[0.7179842533434585, 0.3406003594667248], [0.05138889342234639, 0.025867229487245364], (0.7242990732192993, 0.7242990732192993, 0.03693920746445656)], u'twist3_leg_right_upperLeg_ctr': [[0.34000261742986965, 0.656762544491613], [0.04583333336708847, 0.022469139701829066], (0.027883177623152733, 0.18752333521842957, 0.5467289686203003)], u'foot_left_toeD3_fk_ctr': [[0.5923368893643212, 0.9243779098078976], [0.015058504728263719, 0.01594009898076454], (0.0555325411260128, 0.34599998593330383, 0.017645977437496185), u"\nif cmds.getAttr('%s_leg_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'spine_1_fk_ctr': [[0.39272377927605606, 0.4846406306746605], [0.21455244144788788, 0.023355068113088073], (0.6214953064918518, 0.03162272647023201, 0.03162272647023201)], u'fingerD2_left_ctr': [[0.7456360566238015, 0.6066192975249884], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'fingerE3_right_ctr': [[0.22422139320030735, 0.6254713355971852], [0.014158970777387703, 0.01439040583730907], (0.03360280394554138, 0.2259896695613861, 0.65887850522995)], u'hand_right_hand_fk_ctr': [[0.22603273192477735, 0.5126160685007984], [0.06251153636275879, 0.07052107478583884], (0.03360280394554138, 0.2259896695613861, 0.65887850522995), u"\nif cmds.getAttr('%s_arm_right_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'hand_left_hand_fk_ctr': [[0.7114557317124639, 0.5126160685007984], [0.0625115363627587, 0.07052107478583884], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418), u"\nif cmds.getAttr('%s_arm_left_attrShape.ikFk' % self.chName):\n    controller = controller.replace('fk', 'ik')\n"], u'fingerC2_left_ctr': [[0.7287989733284244, 0.6066192975249884], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)], u'ik_arm_right_pole_ctr': [[0.15821340924446756, 0.3365941392271075], [0.03750000000000001, 0.03749999999999994], (0.6214953064918518, 0.03162272647023201, 0.03162272647023201)], u'neckHead_neck_1_fk_ctr': [[0.46112821092874734, 0.17017620650660034], [0.07774357814250532, 0.021231880014487132], (0.6214953064918518, 0.03162272647023201, 0.03162272647023201)], u'fingerE2_left_ctr': [[0.761619636022305, 0.6066192975249884], [0.014158970777387777, 0.01439040583730907], (0.09149924665689468, 0.5700934529304504, 0.029074732214212418)]}
    size = 800
    idCallBack = []
    def __init__(self, chName, dock=True):
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
            # Review: do not work well if not dockable FIXME
            # add a layout
            dlgLayout = QtWidgets.QVBoxLayout(parent)

        parent.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        super(PickerUI, self).__init__(parent=parent)
        self.parent().layout().addWidget(self)  # add widget finding previously the parent

        # delete on close
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        # when parent is destroyed, child launch close method. we connect the signals.
        parent.destroyed.connect(self.close)

        # chName attribute
        self.chName = chName

        self.buildUI()

        # callBack
        #self.idCallBack.append(OpenMaya.MEventMessage.addEventCallback('SceneOpened', self. __refresh))
        #self.idCallBack.append(OpenMaya.MEventMessage.addEventCallback('NameChanged', self. __refresh))

    def buildUI(self):
        # layout
        generalGrid = QtWidgets.QGridLayout(self)

        buttonsArea = QtWidgets.QWidget()
        buttonsArea.setMinimumSize(self.size, self.size)
        buttonsArea.setMaximumSize(self.size, self.size)
        self.setAcceptDrops(True)  # accept drag and drop, necessary for move buttons

        # container
        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setAlignment(QtCore.Qt.AlignJustify)
        # Apply to scrollWidget
        scrollArea.setWidget(buttonsArea)
        generalGrid.addWidget(scrollArea, 0, 0)

        # buttons
        for controller, data in self.controllerDict.items():
            button = dragButton('', buttonsArea)
            # button command, if data len greater than 3, we have extra info
            command = partial(self._buttonSelect, controller) if len(data)<4 else partial(self._buttonSelect, controller=controller, extraCode=data[3])
            button.released.connect(command)
            # set size
            button.setMinimumSize(data[1][0] * self.size, data[1][1]*self.size)
            button.setMaximumSize(data[1][0] * self.size, data[1][1]*self.size)
            # set position
            button.move(data[0][0]*self.size, data[0][1]*self.size)
            # set color
            button.setAutoFillBackground(True)
            palette = button.palette()
            palette.setColor(QtGui.QPalette.Button, QtGui.QColor(data[2][0]*255, data[2][1]*255, data[2][2]*255, 255))
            button.setPalette(palette)


    def _buttonSelect(self, controller, extraCode=None):
        """
        Button selection method
        :param controller:
        :param extraCode:
        :return:
        """
        if extraCode:
            print controller, extraCode
            exec(extraCode)

        object = '%s_%s' % (self.chName, controller)
        # select command
        # info about the keys
        modifier = cmds.getModifiers()
        noKey = modifier == 0
        shift = modifier == 1
        control = modifier == 4
        # combined keys
        controlShift = modifier == 5

        logger.debug('Modifier value: %s' % modifier)
        logger.debug('shift: %s' % shift)
        logger.debug('control: %s' % control)
        logger.debug('controlShift: %s' % controlShift)

        # select command
        cmds.select(object, r=noKey, tgl=shift, add=controlShift, d=control)
        print 'Select %s' % object


    # when close event, delete callbacks
    def closeEvent(self, event):
        for i, val in enumerate(self.idCallBack):
            # Event callback
            try:
                OpenMaya.MMessage.removeCallback(val)
                logger.debug('MMessage Callback removed: %s' % i)
            except:
                pass

## UTILS ##
def getControllerButtons():
    """
    {controllerName:[[position],[size]], ... }
    TODO: add color
    :return: controllers
    """
    normalizeValue = 12.0
    meshes = cmds.ls(type='mesh')
    controllers = {}

    # get controller info
    for mesh in meshes:
        meshInfo=[]
        # get transform
        transform = cmds.listRelatives(mesh, p=True)[0]
        # position
        bbox = cmds.xform(transform, boundingBox=True, ws=True, q=True)
        position = [bbox[0]/normalizeValue, bbox[2]/normalizeValue]
        meshInfo.append(position)

        # calculate size
        size = [math.fabs((bbox[3] - bbox[0]) / normalizeValue), math.fabs((bbox[2] - bbox[5]) / normalizeValue)]
        meshInfo.append(size)

        # color
        color = cmds.getAttr('%s.overrideColorRGB' % mesh)[0]
        meshInfo.append(color)

        # extra info
        if cmds.attributeQuery('picker', node=transform, ex=True):
            attrValue = cmds.getAttr('%s.picker' % transform)
            meshInfo.append(attrValue)

        # save controller to dictionary
        controllers[transform] = meshInfo

    return controllers

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
    qtCtrl = OpenMayaUI.MQtUtil_findControl(ctrl)
    # translate to something python understand
    ptr = wrapInstance(long(qtCtrl), QtWidgets.QWidget)

    return ptr

def deleteDock(name = 'PickerUIDock'):
    if pm.workspaceControl(name, query=True, exists=True):
        pm.deleteUI(name)

def getMayaWindow():
    #get maya main window
    win = OpenMayaUI.MQtUtil_mainWindow()
    ptr = wrapInstance(long(win), QtWidgets.QMainWindow)

    return ptr

"""
from FbxExporter import FbxExporterUI
from FbxExporter import FbxExporter
reload(FbxExporter)
reload(FbxExporterUI)
ui = FbxExporterUI.FbxExporterUI(True)
"""