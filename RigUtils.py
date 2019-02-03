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

def snapIkFk(controller):
    """
    snap ik fk or fk ik
    :param controller(str or pm): Controller with ikFk shape attribute
    :return:
    """
    # check type
    if isinstance(controller, str):
        ikCtr = pm.PyNode(controller)

    ########################################
    ## Find all controls and main objects ##
    ########################################

    # get locator shape, it is common in all ik and fk controllers.
    # also it has the ikFk info
    locatorS = ikCtr.listRelatives(s=True, type=pm.nodetypes.Locator)[0]
    logger.debug('locatorS: %s' % locatorS)
    if not locatorS:
        logger.info('is not a ik fk chain')
        return

    # ikFk attribute value
    ikFkAttr = locatorS.ikFk

    instances = locatorS.getInstances()
    logger.debug('locator instances: %s' % instances)
    ikCtrList = []  # system ik controllers
    fkCtrList = []  # # system Fk controllers
    # get controllers from instances of locator
    for i in instances:
        controller = i.split('|')[-2]
        controller = pm.PyNode(controller)
        if 'ik' in str(controller):
            ikCtrList.append(controller)
        elif 'fk' in str(controller):
            fkCtrList.append(controller)

    # reverse lists, from nearest to world to last child
    ikCtrList = list(reversed(ikCtrList))
    fkCtrList = list(reversed(fkCtrList))

    # ik Stretch node with stretch value
    ikStretchNode = None
    try:
        # use top fk controller, because it has the correct base name of the system.
        ikStretchNode = str(fkCtrList[0]).split('_')[0:3]  # base name of the system
        ikStretchNode = pm.PyNode('_'.join(ikStretchNode+['ikStretch','stretchValue','condition'])) # name of the stretch ik node
    except:
        pass

    # get system main joints
    mainJointList = [pm.PyNode(str(fk).replace('fk', 'main').replace('ctr', 'joint')) for fk in fkCtrList]

    # get pole controller
    ikHandle = ikCtrList[0].listRelatives(ad=True, type='ikHandle')[0]
    poleConstraint = ikHandle.poleVectorX.inputs(type='constraint')[0]
    pole = poleConstraint.target[0].targetTranslate.inputs(type='transform')[0]

    ## find child controllers, fingers, foot controllers, etc ##
    ikChildList = [ctr.getTransform() for ctr in ikCtrList[0].listRelatives(ad=True, type='nurbsCurve') if
                ctr.getTransform() not in ikCtrList]
    fkChildList = [ctr.getTransform() for ctr in fkCtrList[0].listRelatives(ad=True, type='nurbsCurve') if
               ctr.getTransform() not in fkCtrList]
    mainChildList = [ctr for ctr in mainJointList[0].listRelatives(ad=True, type='joint') if ctr not in mainJointList]

    ikChildCommonCtr = []
    fkChildCommonCtr = []
    ikFkChildCommonCtr = []  # [ikCtrA, fkCtrA, ikCtrB, fkctrB,...] controllers only appear in ik and fk chains
    mainChildCommonJnt = []
    # get common controllers between lists
    # copy of the fkChils list, because we are going to delete members
    for i, fkCtr in enumerate(list(fkChildList)):
        # ask if the given sttr is in the list
        try:
            # it is possible some ctr in ik and fk, but not in main, like generaToe ctr
            ikCtr = pm.PyNode(str(fkCtr).replace('fk', 'ik'))
            try:
                # try if it exists in main too
                mainJnt = pm.PyNode(str(fkCtr).replace('fk', 'main').replace('ctr', 'joint'))
                mainChildCommonJnt.append(mainJnt)
                mainChildList.remove(mainJnt)
            except:
                # if controller is not in main, it is a special controller, only for ik and fk chains
                ikFkChildCommonCtr.append(ikCtr)
                ikFkChildCommonCtr.append(fkCtr)
                fkChildList.remove(fkCtr)
                ikChildList.remove(ikCtr)
                # continue next loop
                continue
            # append to common lists
            fkChildCommonCtr.append(fkCtr)
            ikChildCommonCtr.append(ikCtr)
            # remove from child lists
            fkChildList.remove(fkCtr)
            ikChildList.remove(ikCtr)

        except:
            pass

    # find possible parents of the system, p.e clavicle
    # use the skin skeleton, because it has a more clean hierarchy and it is easiest
    skinJoint = pm.PyNode(str(fkCtrList[0]).replace('fk', 'skin').replace('ctr', 'joint'))
    parentJoint = skinJoint.firstParent()  # first parent for the test
    parentFkCtrList = []
    # iterate over the parents to find valid system parents, like clavicle
    # valid parents only can have 1 joint child
    while True:
        childCount = parentJoint.getChildren(type='joint')
        if len(childCount) > 1:
            # more than 1 child joint, isn't valid
            logger.debug('No parent ctr found')
            break
        else:
            try:
                parentCtr = pm.PyNode(str(parentJoint).replace('skin', 'fk').replace('joint','ctr'))
            except:
                # do not exists a valid ctr, break the iteration
                logger.debug('No parent ctr found')
                break
            # save the control and try another joint
            parentFkCtrList.append(parentCtr)
            parentJoint = parentJoint.firstParent()

    ##########
    #ik -> fk#
    ##########
    if ikFkAttr.get():
        # parent ctr, like clavicles
        if parentFkCtrList:
            parentRotation = parentFkCtrList[0].getRotation('world')
            zoneName = str(parentFkCtrList[0]).split('_')[1]  # zone str name
            try:
                # try if it has an auto attribute, if system does not has an auto attribute,
                # it is not necessary apply rotation
                locatorS.attr('auto%s' % zoneName.capitalize()).set(0)
                parentFkCtrList[0].setRotation(parentRotation, 'world')
            except:
                pass

        # copy stretch factor, if the system has stretch option
        if ikStretchNode:
            locatorS.fkStretch.set(ikStretchNode.outColorR.get())

        # copy rotation from main joints
        for i, mainj in enumerate(mainJointList):
            fkCtrList[i].setRotation(mainj.getRotation())
            # cmds.xform(fkControllers[i], a=True, eu=True, ro=cmds.xform(mainj, a=True, eu=True, q=True, ro=True))

        # last system ctr, foot or hand
        # if we have ikChilds, we have a foot system, so we snap to 'ball' controller (the last)
        if ikChildList:
            #print 'ballCtr', ikChildList[-1]
            fkCtrList[-1].setRotation(ikChildList[-1].getRotation('world'), 'world')

        # ikFk exclusive controllers
        #for i in range(0, len(ikFkChildCommonCtr), 2):
            #ikFkChildCommonCtr[i+1].setRotation(ikFkChildCommonCtr[i].getRotation('world'), 'world')

        # ik Fk main common ctrllers, general first
        for i, fkCtr in enumerate(fkChildCommonCtr):
            fkCtr.setRotation(mainChildCommonJnt[i].getRotation('world'), 'world')

        ikFkAttr.set(0)

    ##########
    #fk -> ik#
    ##########
    elif not ikFkAttr.get():
        # reset walk values
        if ikChildList:  # ikControllers only just like walk controllers
            ikCtrAttributes = pm.listAttr(ikCtrList[0], ud=True, k=True)
            for attr in ikCtrAttributes:
                ikCtrList[0].attr('%s' % attr).set(0)

            # set ikChildCtr to 0
            for ikCtr in ikChildList:
                ikCtr.setRotation((0,0,0))

        pm.xform(ikCtrList[0], ws=True, m=pm.xform(fkCtrList[-1], q=True, ws=True, m=True))

        # ikFk exclusive controllers
        for i in range(0, len(ikFkChildCommonCtr), 2):
            ikFkChildCommonCtr[i+1].setRotation(ikFkChildCommonCtr[i].getRotation('world'), 'world')

        # ikFk exclusive controllers
        for i in range(0, len(ikFkChildCommonCtr), 2):
            ikFkChildCommonCtr[i].setRotation(ikFkChildCommonCtr[i+1].getRotation('world'), 'world')

        # ik Fk main common ctrllers, general first
        for i, ikCtr in enumerate(ikChildCommonCtr):
            ikCtr.setRotation(mainChildCommonJnt[i].getRotation('world'), 'world')

        if pole:
            # poleVector, use vector additive propriety
            upperLegPos = mainJointList[0].getTranslation('world')
            lowerLegPos = mainJointList[1].getTranslation('world')
            footPos = mainJointList[2].getTranslation('world')

            vector1 = pm.datatypes.Vector(lowerLegPos-upperLegPos)
            vector1.normalize()

            vector2 = pm.datatypes.Vector(lowerLegPos - footPos)
            vector2.normalize()

            poleVectorPos = vector1 + vector2
            poleVectorPos.normalize()
            # multiply the resultant vector by the value we want, this way we can control the distance
            poleVectorPos = poleVectorPos * 20

            # set pole vector position
            pole.setTranslation(poleVectorPos+lowerLegPos, 'world')

        ikFkAttr.set(1)


def neckHeadIsolateSnap(name, zone, controller, point, orient):
    """
    TODO: valid with only 1 argument
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

