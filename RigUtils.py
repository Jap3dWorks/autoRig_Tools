from maya import cmds
from maya import OpenMaya
from maya import OpenMayaAnim
from maya import mel
import re
import pymel.core as pm
import math
import ARCore

import logging
logging.basicConfig()
logger = logging.getLogger('RigUtils:')
logger.setLevel(logging.DEBUG)


# todo: pymel mode all
def snapIkFk(name, zoneA, zoneB, zoneC, side):
    """
    snap ik fk or fk ik
    args:
        TODO: zonesList[]->no multiple parameters
        TODO: find scale factor node/value
        name(str): character name
        zoneA(str): zone to snap p.e leg, arm
        zoneB(str): zone below zoneA to snap p.e foot, hand
        zoneC(str): zone below zoneB to snap p.e toe, finger
        side(str): left or right
    """
    # TODO rewrite this method, adapting it to name convention and with only one input FIXME
    attrShape = '%s_%s_%s_attrShape' % (name, side, zoneA)
    attrValue = cmds.getAttr('%s.ikFk' % attrShape)

    #Fixme: fix name convention expressions
    # find fk ik Controllers and main
    fkControllers = [i for i in cmds.ls() if
                     re.match('^%s_fk_(%s|%s)_*%s_((?!end).).*ctr$' % (name, zoneA, zoneB, side), str(i))]
    ikControllers = [i for i in cmds.ls() if
                     re.match('^%s_ik_(%s|%s)_*%s_((?!end).).*ctr$' % (name, zoneA, zoneB, side), str(i))]
    mainJoints = [i for i in cmds.ls() if
                  re.match('^%s_main_(%s|%s)_*%s_((?!end).).*joint$' % (name, zoneA, zoneB, side), str(i))]

    ikMatchControllers = []  # controls that are common
    fkMatchControllers = []  # controls that are common
    mainMatchControllers = []  # controls that are common
    poleVectorCtr = None  # pole vector ctr
    ikToeGeneral = None  # general toes control ik
    fkToeGeneral = None  # general toes control fk
    ikFootCtr = None  # ik foot control
    mainFootJoint = None  # main foot joint
    fkFootCtr = None  # fk foot control
    ikBallCtr = None
    # arrange lists to be synchronized
    for ikCtr in list(ikControllers):
        try:
            mainIndex = mainJoints.index(ikCtr.replace('ik', 'main').replace('ctr', 'joint'))
            fkIndex = fkControllers.index(ikCtr.replace('ik', 'fk'))

            if ikCtr == '%s_ik_%s_%s_%s_ctr' % (name, zoneB, side, zoneB):
                ikFootCtr = ikCtr
                ikControllers.remove(ikCtr)
                mainFootJoint = mainJoints.pop(mainIndex)
                fkFootCtr = fkControllers.pop(fkIndex)

            else:
                mainMatchControllers.append(mainJoints.pop(mainIndex))
                fkMatchControllers.append(fkControllers.pop(fkIndex))
                ikMatchControllers.append(ikCtr)
                ikControllers.remove(ikCtr)

        except:
            if 'pole' in ikCtr:
                poleVectorCtr = ikCtr
                ikControllers.remove(ikCtr)

            if 'ball' in ikCtr.lower():
                ikBallCtr = ikCtr

            elif zoneC and '%sGeneral' % zoneC in ikCtr:
                ikToeGeneral = ikCtr
                ikControllers.remove(ikCtr)

                elemetnIndex = fkControllers.index(ikCtr.replace('ik', 'fk'))
                fkToeGeneral = fkControllers.pop(elemetnIndex)

    # ik -> fk
    if attrValue:
        # copy rotation from main joints, this can give som errors in toes, because main joints does not has general toe ctr
        # so we exclude foot and toes
        for i, mainj in enumerate(mainJoints):
            cmds.xform(fkControllers[i], a=True, eu=True, ro=cmds.xform(mainj, a=True, eu=True, q=True, ro=True))

        ikFkCtr = ikBallCtr if ikBallCtr else ikFootCtr  # if we have ikBall use it for the snap
        cmds.xform(fkFootCtr, a=True, ws=True, ro=cmds.xform(ikFkCtr, a=True, ws=True, q=True, ro=True))
        cmds.xform(fkToeGeneral, a=True, ro=cmds.xform(ikToeGeneral, q=True, a=True, ro=True))
        # controllers that match between ik, fk and main.
        for i, fkCtr in enumerate(fkMatchControllers):
            cmds.xform(fkCtr, ws=True, m=cmds.xform(ikMatchControllers[i], ws=True, q=True, m=True))

        cmds.setAttr('%s.ikFk' % attrShape, not attrValue)

    # fk -> ik
    elif not attrValue:
        # reset walk values
        if ikControllers:  # ikControllers only just left walk controllers
            for attr in ('heel', 'tilt', 'toes', 'ball', 'footRoll'):
                cmds.setAttr('%s.%s' % (ikFootCtr, attr), 0)
                if attr == 'tilt':  # we have two tilts
                    for inOut in ('In', 'Out'):
                        ctrIndex = ikControllers.index(
                            '%s_ik_foot_%s_foot%s%s_ctr' % (name, side, attr.capitalize(), inOut))
                        cmds.xform(ikControllers[ctrIndex], a=True, t=(0, 0, 0), ro=(0, 0, 0), s=(1, 1, 1))
                elif attr == 'footRoll':
                    continue
                else:
                    ctrIndex = ikControllers.index('%s_ik_%s_%s_foot%s_ctr' % (name, zoneB, side, attr.capitalize()))
                    cmds.xform(ikControllers[ctrIndex], a=True, t=(0, 0, 0), ro=(0, 0, 0), s=(1, 1, 1))

        cmds.xform(ikFootCtr, ws=True, m=cmds.xform(fkFootCtr, q=True, ws=True, m=True))
        cmds.xform(ikToeGeneral, a=True, ro=cmds.xform(fkToeGeneral, q=True, a=True, ro=True))
        # snap toes
        for i, ikCtr in enumerate(ikMatchControllers):
            cmds.xform(ikCtr, ws=True, m=cmds.xform(fkMatchControllers[i], ws=True, q=True, m=True))

        if poleVectorCtr:
            # poleVector, use vector additive propriety
            upperLegPos = cmds.xform(mainJoints[0], q=True, ws=True, t=True)
            lowerLegPos = cmds.xform(mainJoints[1], q=True, ws=True, t=True)
            footPos = cmds.xform(mainFootJoint, q=True, ws=True, t=True)

            vector1 = OpenMaya.MVector(lowerLegPos[0] - upperLegPos[0], lowerLegPos[1] - upperLegPos[1],
                                       lowerLegPos[2] - upperLegPos[2])
            vector1.normalize()
            vector2 = OpenMaya.MVector(lowerLegPos[0] - footPos[0], lowerLegPos[1] - footPos[1],
                                       lowerLegPos[2] - footPos[2])
            vector2.normalize()

            poleVectorPos = vector1 + vector2
            poleVectorPos.normalize()
            # multiply the resultant vector by the value we want, this way we can control the distance
            poleVectorPos = poleVectorPos * 20

            # set pole vector position
            cmds.xform(poleVectorCtr, ws=True, t=(
            poleVectorPos.x + lowerLegPos[0], poleVectorPos.y + lowerLegPos[1], poleVectorPos.z + lowerLegPos[2]))

        cmds.setAttr('%s.ikFk' % attrShape, not attrValue)

"""
if __name__ == '__main__':
    snapIkFk('akona', 'leg', 'foot', 'toe', 'left')


import pymel.core as pm
# create 2 cubes, pcube1 and pCube2 with diferent orientations but the same shape position
cube01 = pm.PyNode('pCube1')
cube02 = pm.PyNode('pCube2')

Offset = cube01.getRotation(space='world', quaternion=True)*cube02.getRotation(space='world', quaternion=True).invertIt()
print Offset

Offset.invertIt()

# now rotate cube 1 and apply the line below
cube02.setRotation(Offset*cube01.getRotation(space='world', quaternion=True), 'world')
"""

def neckHeadIsolateSnap(name, zone, controller, point, orient):
    """
    isolate to 0 or 1 and snap controllers
    args:
        name(str): character name
        zone(str): zone of controller
        controller(str): controller type
        point (bool): if true, snap translation
        orient (bool): if true, snap rotation
    """
    headControl = '%s_IK_%s_%s_1_ctr' % (name, zone, controller)

    # check if exist
    if not cmds.objExists(headControl):
        print ('%s do not exists' % headControl)
        return

    # save transforms
    headControlTranslate = cmds.xform(headControl, q=True, ws=True, m=True)

    if orient:
        # set orient
        print ('set orient')
        isolate = not cmds.getAttr('%s.isolateOrient' % headControl)
        cmds.setAttr('%s.isolateOrient' % headControl, isolate)

    if point:
        # set position
        print ('set point')
        isolate = not cmds.getAttr('%s.isolatePoint' % headControl)
        cmds.setAttr('%s.isolatePoint' % headControl, isolate)

    # Transform head control
    cmds.xform(headControl, ws=True, m=headControlTranslate)


## Proxies ##
# TODO: make class, include in the picker
#UI
def proxyShowUI(name):
    """
    Activate proxies UI
    Args:
        name(str): name of the character
    """
    windowName = '%sShowProxiesUI' % name.capitalize()
    # check if window exists
    if cmds.window(windowName, q=True, exists=True):
        cmds.deleteUI(windowName)

    cmds.window(windowName)

    # proxy str
    proxyStr = 'proxy'

    # def window
    column = cmds.columnLayout(adj=True, co=('both', 10))
    cmds.text(label='%s Proxies' % name.capitalize())
    cmds.separator(visible=True, h=20)

    # row layout to store chBox and button
    cmds.rowLayout(nc=2, adjustableColumn=2)

    # check state
    parent, state = checkState(name, proxyStr)

    # ui widgets
    chBox = cmds.checkBox(label='Parent', value=parent, enable=not state)
    buttonName = 'Model' if state else 'Proxies'
    button = cmds.button(buttonName, command=lambda x: proxyShowUIButton(name, chBox, button, proxyStr))

    # show window
    cmds.showWindow()


def proxyShowUIButton(name, chBox, button, proxyStr, *args):
    """
    UI proxies button, turn on or off proxies.
    Args:
        name(str): name of the character
        chBox(str): UI checkBox
        button(str): UI button
        proxyStr(str): common word for all the proxies
        *args:
    """
    chBoxValue = cmds.checkBox(chBox, q=True, v=True)

    # list proxies
    proxyList = cmds.ls('*%s' % proxyStr, type='transform')

    # connect proxies by parenting
    if chBoxValue:
        value = proxyModelParent(name, proxyList, proxyStr)
    # connect proxies by constraint
    else:
        value = proxyModelConstraints(name, proxyList, proxyStr)

    # change button name and disable chBox
    if value:
        cmds.button(button, e=True, label='Model')
        cmds.checkBox(chBox, e=True, enable=False)
    # change button name and enable chBox
    else:
        cmds.button(button, e=True, label='Proxies')
        cmds.checkBox(chBox, e=True, enable=True)


def checkState(name, proxyStr):
    """
    check the state of the proxies
    return:
        (bool): True, parent. False, constraint
        (bool): True, proxies active. False, model active
    """
    proxyGrp = '%s_%s_grp' % (name, proxyStr)
    proxyConstraints = cmds.listRelatives(proxyGrp, ad=True, type='constraint')
    proxyTransforms = [proxy for proxy in cmds.listRelatives('%s_rig_grp' % name, ad=True, type='transform') if
                       proxyStr in proxy]

    if proxyConstraints:
        return False, True
    elif proxyTransforms:
        return True, True
    else:
        return False, False


# proxy scripts
def proxyModelConstraints(name, proxies, proxyStr):
    """
    Connect proxy models to deform joints by constraints
    Args:
        name(str): name of the character
        proxies(list(str)): list with proxies
        proxyStr(str): common word for all the proxies
    """
    proxyGrp = '%s_%s_grp' % (name, proxyStr)
    proxyConstraints = cmds.listRelatives(proxyGrp, ad=True, type='constraint')

    # disconnect proxies
    if proxyConstraints:
        ProxyDisconnectConstraints(name, 0)
        cmds.delete(proxyConstraints)
        cmds.setAttr('%s.visibility' % proxyGrp, 0)
        return False  # useful to change elements of the ui

    # connect proxies
    else:
        ProxyDisconnectConstraints(name, 1)
        cmds.setAttr('%s.visibility' % proxyGrp, 1)
        for proxy in proxies:
            try:
                mainName = proxy.replace(proxyStr, 'main')
                cmds.parentConstraint(mainName, proxy, maintainOffset=False)
                cmds.scaleConstraint(mainName, proxy, maintainOffset=False)
            except:
                ctrName = proxy.replace(proxyStr, 'ctr')
                cmds.parentConstraint(ctrName, proxy, maintainOffset=False)
                cmds.scaleConstraint(ctrName, proxy, maintainOffset=False)
        return True  # useful to change elements of the ui


def proxyModelParent(name, proxies, proxyStr):
    """
    Connect proxy models to deform joints by parenting them
    Args:
        name(str): name of the character
        proxies(list(str)): list with proxies
        proxyStr(str): common word for all the proxies
    """
    proxyTransforms = [proxy for proxy in cmds.listRelatives('%s_rig_grp' % name, ad=True, type='transform') if
                       proxyStr in proxy]
    proxyGrp = '%s_%s_grp' % (name, proxyStr)

    # unparent proxies
    if proxyTransforms:
        ProxyDisconnectConstraints(name, 0)  # 1 connect
        cmds.parent(proxyTransforms, '%s_%s_grp' % (name, proxyStr))
        cmds.setAttr('%s.visibility' % proxyGrp, 0)
        return False  # useful to change elements of the ui

    # parent proxies
    else:
        ProxyDisconnectConstraints(name, 1)  # 1 disconnect
        for proxy in proxies:
            try:
                mainName = proxy.replace(proxyStr, 'main')
                cmds.parent(proxy, mainName)
                cmds.xform(proxy, os=True, t=(0, 0, 0), ro=(0, 0, 0), s=(1, 1, 1))
            except:
                ctrName = proxy.replace(proxyStr, 'ctr')
                cmds.parent(proxy, ctrName)
                cmds.xform(proxy, os=True, t=(0, 0, 0), ro=(0, 0, 0), s=(1, 1, 1))
        return True  # useful to change elements of the ui


def ProxyDisconnectConstraints(name, value):
    """
    Turn off all deformable joint constraints, and skinClusters
    Args:
        name(str): Character name
        value(int): 1->disconnect, 0->connect
    """
    jointsGrp = '%s_joints_grp' % name
    modelGrp = '%s_model_grp' % name
    constraints = cmds.ls(jointsGrp, dag=True, type='constraint')
    meshList = cmds.ls(modelGrp, dag=True, type='mesh')

    # groups visibility
    cmds.setAttr('%s.visibility' % jointsGrp, not value)
    cmds.setAttr('%s.visibility' % modelGrp, not value)

    for constraint in constraints:
        cmds.setAttr('%s.nodeState' % constraint, value)  # disconnect
        cmds.setAttr('%s.frozen' % constraint, value)

    for mesh in meshList:
        skinNode = cmds.listConnections(mesh, d=True, type='skinCluster')
        if skinNode:
            cmds.setAttr('%s.nodeState' % skinNode[0], value)  # disconnect
            cmds.setAttr('%s.frozen' % skinNode[0], value)
"""
if __name__ == '__main__':
    proxyShowUI('akona')
"""

