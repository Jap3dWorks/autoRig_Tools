# tools for use the rig

from maya import cmds
from maya import OpenMaya
from maya import OpenMayaAnim
from maya import mel
import re
import pymel.core as pm
import math

import logging
logging.basicConfig()
logger = logging.getLogger('rigTools:')
logger.setLevel(logging.DEBUG)


def twistBonesCreator(sections):
    """
    select joints, create twist bones from selected joints to its children
    Args:
        number(int): number twist bones

    Returns(list): twist joints
    """
    selection = pm.ls(sl=True)
    for sel in selection:
        totalNewJoints = []

        if not isinstance(sel, pm.nodetypes.Joint):
            continue
        child = sel.childAtIndex(0)

        value = child.translateX.get() / sections

        twistJoints = [sel]
        for i in range(sections):

            nameList = str(sel).split('_')
            nameList.insert(2, 'twist%s' %(i+1))
            nameTwist=nameList.pop(0)
            for name in nameList:
                nameTwist += '_%s' %name

            twistJoint = sel.duplicate(po=True, name=nameTwist)[0]
            twistJoints[-1].addChild(twistJoint)
            twistJoint.translateX.set(value)
            twistJoints.append(twistJoint)

            if i == sections - 1:
                # last joint bigger
                twistJoint.radius.set(3)

        twistJoints[-1].addChild(child)
        totalNewJoints += twistJoints[1:]

    return totalNewJoints

def snapIkFk(name, zoneA, zoneB, zoneC, side):
    """
    snap ik fk or fk ik
    args:
        name(str): character name
        zoneA(str): zone to snap p.e leg, arm
        zoneB(str): zone below zoneA to snap p.e foot, hand
        zoneC(str): zone below zoneB to snap p.e toe, finger
        side(str): left or right
    """
    # TODO rewrite this method, adapting it to name convention and with only one input FIXME
    attrShape = '%s_%s_%s_attrShape' % (name, zoneA, side)
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


## PSDs ##
class PSDUtils(object):
    @staticmethod
    def extractPosesPoseEditor():
        poseSelection = pm.ls(sl=True)
        for poseSel in poseSelection:
            poses = pm.poseInterpolator(poseSel, q=True, poseNames=True)

            # get Blendshape node
            poseSelShape = poseSel.getShape()
            blendShapeNode = poseSelShape.output.outputs()[0]

            mesh = pm.PyNode(blendShapeNode.getGeometry()[0])
            meshTransform = mesh.getTransform()

            for pose in poses:
                if pose == 'neutral' or pose == 'neutralSwing' or pose == 'neutralTwist':
                    continue

                pm.poseInterpolator(poseSel, edit=True, goToPose=pose)

                # duplicate geo
                meshDup = meshTransform.duplicate()[0]
                meshDup.setParent(w=True)
                meshDup.rename(pose + '_mesh')

            pm.poseInterpolator(poseSel, edit=True, goToPose='neutral')

    @staticmethod
    def deltaCorrective(joints, bShape):
        """
        extract and apply delto to a blendShape
        """

        mesh = pm.PyNode(bShape.getGeometry()[0])
        meshTransform = mesh.getTransform()

        for joint in joints:
            # create poseInterpolator
            poseInterpolator = pm.PyNode(pm.poseInterpolator(joint, name=str(joint) + '_poseInterpolator')[0])
            poseInterpolatorShape = poseInterpolator.getShape()
            print poseInterpolator

            # create basic poses
            for i, pose in enumerate(['neutral', 'neutralSwing', 'neutralTwist']):
                pm.poseInterpolator(poseInterpolator, e=True, addPose=pose)
                poseInterpolatorShape.pose[i].poseType.set(i)

            for rot in ([0, 90, 0], [0, -90, 0], [0, 0, 90], [0, 0, -90]):
                baseMesh = meshTransform.duplicate(name=str(joint) + ('_baseMesh'))[0]
                baseMesh.setParent(w=True)

                joint.setRotation(rot, 'object')
                negativeMesh = meshTransform.duplicate(name=str(joint) + ('_negative'))[0]
                negativeMesh.setParent(w=True)
                joint.setRotation([0, 0, 0], 'object')

                deltaMush = cmds.deltaMush(str(meshTransform), si=180, ss=0.1)
                cmds.dgeval(deltaMush)
                # set poses
                joint.setRotation(rot, 'object')
                namePose = str(joint) + ('_%s_%s_%s' % (rot[0], rot[1], rot[2])).replace('-', 'n')
                pm.poseInterpolator(poseInterpolator, e=True, addPose=namePose)

                # duplicate mesh
                positive = meshTransform.duplicate(name=namePose)[0]
                positive.setParent(w=True)

                # get delta
                deltaShape = PSDUtils.getDelta(positive.getShape(), negativeMesh.getShape(), baseMesh.getShape())

                pm.delete(baseMesh)
                cmds.delete(deltaMush)

                # create bShape
                weightIndex = bShape.numWeights()
                bShape.addTarget(mesh, weightIndex, deltaShape, 1.0)

                joint.setRotation([0, 0, 0], 'object')

    @staticmethod
    def getDelta(positive, negative, base):
        """
        Extract a delta from a sculpted position mesh. less precise
        positive(pm.mesh): posed sculpted mesh
        negative(pm.mesh): posed mesh
        base(pm.Mesh): non posed and non sculpted mesh
        """
        diferenceIndex = []
        for i, point in enumerate(positive.getPoints('object')):
            if point != negative.getPoint(i, 'object'):
                diferenceIndex.append(i)

        # duplicate base mesh
        baseDup = base.duplicate()[0].getShape()

        util = OpenMaya.MScriptUtil()

        sel = OpenMaya.MSelectionList()
        for i in (negative, base):
            sel.add(str(i))

        # negative
        mObject = OpenMaya.MObject()
        sel.getDependNode(0, mObject)
        negativeMFN = OpenMaya.MFnMesh(mObject)
        negativeIt = OpenMaya.MItMeshVertex(mObject)

        # base
        BmObject = OpenMaya.MObject()
        sel.getDependNode(1, BmObject)
        baseMFN = OpenMaya.MFnMesh(BmObject)
        baseIt = OpenMaya.MItMeshVertex(BmObject)

        # store tangents and biNormals
        negativeTVec = OpenMaya.MVectorArray()
        baseTVec = OpenMaya.MVectorArray()

        negBiNorVec = OpenMaya.MVectorArray()
        baseBiNorVec = OpenMaya.MVectorArray()

        # get Tangents
        for i in diferenceIndex:
            floatVector = OpenMaya.MVector()
            floatBiNormal = OpenMaya.MVector()
            baseVector = OpenMaya.MVector()
            baseBiNormal = OpenMaya.MVector()

            ptr = util.asIntPtr()
            negativeIt.setIndex(i, ptr)
            faces = OpenMaya.MIntArray()
            negativeIt.getConnectedFaces(faces)

            negativeMFN.getFaceVertexTangent(faces[0], i, floatVector)
            negativeMFN.getFaceVertexBinormal(faces[0], i, floatBiNormal)

            baseMFN.getFaceVertexTangent(faces[0], i, baseVector)
            baseMFN.getFaceVertexBinormal(faces[0], i, baseBiNormal)

            negativeTVec.append(floatVector)
            negBiNorVec.append(floatBiNormal)
            baseTVec.append(baseVector)
            baseBiNorVec.append(baseBiNormal)

        # apply martix transforms
        for n, i in enumerate(diferenceIndex):
            # negative
            normal = OpenMaya.MVector()
            negativeMFN.getVertexNormal(i, normal)
            binormal = negBiNorVec[n]
            binormal.normalize()
            tangent = negativeTVec[n]
            tangent.normalize()
            matrixSpaceNegative = [normal.x, normal.y, normal.z, 0, tangent.x, tangent.y, tangent.z, 0, binormal.x,
                                   binormal.y, binormal.z, 0, 0, 0, 0, 1]
            matrixNeg = OpenMaya.MMatrix()
            util.createMatrixFromList(matrixSpaceNegative, matrixNeg)

            matrixNeg3x3 = pm.datatypes.MatrixN([[normal.x, normal.y, normal.z], [tangent.x, tangent.y, tangent.z],
                                                 [binormal.x, binormal.y, binormal.z]])

            # base
            normal = OpenMaya.MVector()
            baseMFN.getVertexNormal(i, normal)
            binormal = baseBiNorVec[n]
            binormal.normalize()
            tangent = baseTVec[n]
            tangent.normalize()
            matrixSpaceBase = [normal.x, normal.y, normal.z, 0, tangent.x, tangent.y, tangent.z, 0, binormal.x, binormal.y,
                               binormal.z, 0, 0, 0, 0, 1]
            matrixBas = OpenMaya.MMatrix()
            util.createMatrixFromList(matrixSpaceBase, matrixBas)
            matrixBas3x3 = pm.datatypes.MatrixN([[normal.x, normal.y, normal.z], [tangent.x, tangent.y, tangent.z],
                                                 [binormal.x, binormal.y, binormal.z]])


            # diferenceVector
            vectorPosed = positive.getPoint(i) - negative.getPoint(i)
            vectorPosed = OpenMaya.MVector(vectorPosed[0], vectorPosed[1], vectorPosed[2])
            vectorPosedPM = pm.datatypes.MatrixN([vectorPosed[0], vectorPosed[1], vectorPosed[2]])

            # TODO: calculate real vector length
            # cmds.skinPercent( 'skinCluster1', 'akona_body_mesh.vtx[2702]', transform='akona_foot_left_joint', query=True )

            # baseSpace
            vecNegSpace = vectorPosedPM * matrixNeg3x3.inverse()
            vecBaseSpace = vecNegSpace * matrixBas3x3
            # compare vector length form joint position


            # apply diference
            originalPos = base.getPoint(i, 'object')

            VertexPos = [originalPos[0] + vecBaseSpace[0][0], originalPos[1] + vecBaseSpace[0][1], originalPos[2] + vecBaseSpace[0][2]]
            baseDup.setPoint(i, VertexPos, 'object')

        baseDup.getTransform().rename('delta')
        return baseDup

    @staticmethod
    def getDeltaByJointAngle(positive, negative, skinMesh,  joint):
        """
        FIXME: problems with the total quaternion rotation. data process seems works fine
        Extract a delta from a sculpted position mesh, more precise method
        positive(pm.mesh): posed sculpted mesh
        negative(pm.mesh): posed mesh TODO, this can be unnecessary
        skinMesh(pm.mesh): skined mesh, posed like sculpted mesh. be careful with the input nodes, the skin cluster may be accessible
        joint(pm.Joint): joint rotated for the pose
        """
        diferenceIndex = []
        for i, point in enumerate(positive.getPoints('object')):
            if point != negative.getPoint(i, 'object'):
                diferenceIndex.append(i)

        skinCluster = skinMesh.listConnections(connections=True, type='skinCluster')[0][1]
        skinCluster = pm.PyNode(skinCluster)  # convert to pyNode

        # query angles
        angleQ = joint.getRotation(quaternion=True, space='preTransform')
        worldQ = joint.getRotation(quaternion=True, space='world')
        angleEu = joint.getRotation()  # euler
        angle = math.acos(angleQ[3])*2  # angle Radians
        joint.setRotation([0, 0, 0])
        jointZeroR = joint.getRotation(quaternion=True, space='world')

        jointMatrix = pm.xform(joint, q=True, m=True, ws=True)
        jointMatrix = pm.datatypes.MatrixN([jointMatrix[0], jointMatrix[1], jointMatrix[2]],
                                           [jointMatrix[4], jointMatrix[5], jointMatrix[6]],
                                           [jointMatrix[8], jointMatrix[9], jointMatrix[10]])

        jointOrient = joint.getOrientation()

        # joint position
        jointPos = joint.getTranslation('world')

        # create base pose
        baseMesh = skinMesh.duplicate(name='%s_delta' % str(skinMesh))[0]
        baseMeshShape = baseMesh.getShape()
        joint.setRotation(angleEu)

        for index in diferenceIndex:
            influence = pm.skinPercent(skinCluster, skinMesh.vtx[index], transform=joint, query=True)
            # influence plus influences of child joints
            joinChild = [str(j) for j in joint.listRelatives(ad=True)]
            jointsInfluence = pm.skinPercent(skinCluster, skinMesh.vtx[index], q=True, transform=None)
            matchJoint = set(joinChild).intersection(set(jointsInfluence))
            for j in matchJoint:
                influence += pm.skinPercent(skinCluster, skinMesh.vtx[index], transform=j, query=True)

            # vector from joint to vertex sculpted
            sculptVector = positive.getPoint(index, 'object')
            sculptVector = pm.datatypes.Vector(sculptVector - jointPos)

            # if influence == 0 don't calculate
            if influence:
                angleA = math.pi - (angle/2 + math.pi/2)
                angleB = math.pi - (angle*influence + angleA)
                # with sin rules get the length of final vector
                lengthFVector = sculptVector.length()*math.sin(angleB)/math.sin(angleA)

                # create relative quaternion to influence
                qW = math.cos(angle*(-influence) / 2)
                util = OpenMaya.MScriptUtil()
                util.createFromDouble(angleQ.x, angleQ.y, angleQ.z, qW)
                ptr = util.asDoublePtr()
                relativeQ = pm.datatypes.Quaternion(ptr)

                rotatedVector = sculptVector.rotateBy(relativeQ)
                rotatedVector.normalize()
                rotatedVector = rotatedVector*lengthFVector

                sculptVector = rotatedVector

            baseMeshShape.setPoint(index, sculptVector + jointPos, 'world')

    @staticmethod
    def connectBlendShape(blendshapeNode, blendShapeTarget):
        """
        connect PoseInterpolator with blendShape target
        naming of target: nameChar_identifier_jointName_(side)_"joint"_x_x_x  p.e: akona_cloths_upperLeg_left_joint_0_90_0
        naming of poseInterpolator: nameChar_identifier_jointName_(side)_"joint"_"poseInterpolator"  p.e: akona_upperLeg_left_joint_poseInterpolator
        :return:
        """
        # check type
        if isinstance(blendshapeNode, str):
            blendshapeNode = pm.PyNode(blendshapeNode)

        # construct poseInterpolator node name
        poseInterpolatorName = blendShapeTarget.split('_')
        rotationValues = '_'.join(poseInterpolatorName[-3:])  # name rotation values
        charName = poseInterpolatorName[0]
        poseInterpolatorName = '_'.join(poseInterpolatorName[2:-3])
        # pose interpolator logic is in the shape
        poseInterpolatorName = '%s_%s_poseInterpolatorShape' % (charName, poseInterpolatorName)
        logger.debug('poseInterpolator node: %s' % poseInterpolatorName)

        # check if exists
        try:
            poseIntNode = pm.PyNode(poseInterpolatorName)
        except:
            logger.info('Pose interpolator node %s do not exists' % poseInterpolatorName)
            return

        # pose interpolator output values
        poseIntElements = poseIntNode.output.elements()
        logger.debug('Pose interpolator elements: %s' % poseIntElements)
        for intEl in poseIntElements:
            target = poseIntNode.attr(intEl).outputs(p=True)  # p => plug

            if target:
                target = target[0]
                logger.debug('%s.%s target: %s' % (str(poseIntNode), intEl, target.getAlias()))

                # target rotation name
                targetRotation = '_'.join(target.getAlias().split('_')[-3:])

                # if the rotation values are the same, connect
                if rotationValues == targetRotation:
                    try:
                        # if the attribute is already connected, do nothing
                        poseIntNode.attr(intEl).connect(blendshapeNode.attr(blendShapeTarget))
                        return
                    except:
                        return

    @staticmethod
    def connectBlendShapes(blendshapeNode):
        """
        Search and connect PoseInterpolators with BlendShapes targets
        naming of target: nameChar_identifier_jointName_(side)_"joint"_x_x_x  p.e: akona_cloths_upperLeg_left_joint_0_90_0
        naming of poseInterpolator: nameChar_identifier_jointName_(side)_"joint"_"poseInterpolator"  p.e: akona_upperLeg_left_joint_poseInterpolator
        Arg:
            blendshapeNode: blendShape Node
        :return:
        """
        # check type
        if isinstance(blendshapeNode, str):
            blendshapeNode = pm.PyNode(blendshapeNode)

        blendTargets = blendshapeNode.weight.elements()
        logger.debug(blendTargets)
        for target in blendTargets:
            PSDUtils.connectBlendShape(blendshapeNode, target)


## Proxies ##
# TODO: make class
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

class CopyDeforms(object):
    """
    class with CopyDeform scripts related
    """
    @staticmethod
    def copySkin(skinedMesh, mesh):
        """
        Copy skin cluster from a skined mesh
        """
        # Checks nodetypes
        if not isinstance(skinedMesh, pm.nodetypes.Transform):
            skinedMesh = pm.PyNode(skinedMesh)
        if not isinstance(mesh, pm.nodetypes.Transform):
            mesh = pm.PyNode(mesh)

        # get shape
        skinedMeshShape = skinedMesh.getShape()

        # loop since a skin cluster are found
        skinCluster = pm.listHistory(skinedMeshShape, type='skinCluster')[0]
        # skinCluster = pm.PyNode(skinCluster)
        skinInf = skinCluster.maxInfluences.get()

        # joint list
        jointList = skinCluster.influenceObjects()

        # create skinCluster
        copySkinCluster = pm.skinCluster(mesh, jointList, mi=skinInf)
        print copySkinCluster
        # copy skin weigths
        pm.copySkinWeights(ss=skinCluster, ds=copySkinCluster, noMirror=True, surfaceAssociation='closestPoint',
                           influenceAssociation=('closestJoint', 'closestJoint'))

    @staticmethod
    def copyBlendShape(blendShapeAttr, targetMesh):
        """
        disconnect a blend shape, connect a mesh with a wrap then clone mesh that mesh
        Args:
            blendShapeAttr: blend shape attribute to clone
            targetMesh: target mesh where apply the wrap modifier
        """
        # attribute pymel class
        if not isinstance(blendShapeAttr, pm.general.Attribute):
            blendShapeAttr = pm.PyNode(blendShapeAttr)

        # targetMesh pymel class
        if not isinstance(targetMesh, pm.nodetypes.Transform):
            targetMesh = pm.PyNode(targetMesh)

        # clone target mesh. easily delete wrap later
        targetMeshClone = pm.PyNode(targetMesh.duplicate()[0])

        # Get sourceMesh
        bsNode = pm.PyNode(blendShapeAttr.nodeName())
        meshShape = bsNode.getGeometry()[0]
        meshShape = pm.PyNode(meshShape)
        sourceMesh = meshShape.getTransform()

        # wrap deformer
        cmds.select([str(targetMeshClone), str(sourceMesh)])
        wrapDef=mel.eval('doWrapArgList "2" { "1","0","2.5" }')[0]

        # store connections, and break connections
        parentAttr = blendShapeAttr.getParent(arrays=True)
        elements = parentAttr.elements()
        indexBS = blendShapeAttr.index()  # logical index of the blendShape
        connection = blendShapeAttr.inputs(p=True)
        logger.debug('connections %s: %s' % (blendShapeAttr.getAlias(), connection))
        connection = connection[0]
        connection.disconnect(blendShapeAttr)

        # set blendShape
        blendShapeAttr.set(1)

        # cloneShape
        BShapeTargetMesh = targetMeshClone.duplicate()[0]
        # parent world
        BShapeTargetMesh.setParent(world=True)
        # delete cloned target mesh
        pm.delete(targetMeshClone)

        # reconnect bs
        connection.connect(blendShapeAttr)

        # rename blendShape, Review: Possible naming errors
        attrSplitName = blendShapeAttr.getAlias().split('_')[1:]
        attrSplitName = '_'.join(attrSplitName)
        targetSplitName = str(BShapeTargetMesh).split('_')[:-1]
        targetSplitName = '_'.join(targetSplitName)
        # rename
        BShapeTargetMesh.rename('%s_%s' % (targetSplitName, attrSplitName))

        return BShapeTargetMesh

    @staticmethod
    def copyBlendShapes(blendShapeNode, targetMesh):
        """
        Copy each target from blendShapeNode into targetMesh, using wrap modifier
        Args:
            blendShapeAttr: blend shape attribute to clone
            targetMesh: target mesh where apply the wrap modifier
        Return:
            BlendShapeNode: blend Shape node
            BSNames: List with blend shapes Names
        """
        # check blendshapeNode type
        if not isinstance(blendShapeNode, pm.nodetypes.BlendShape):
            blendShapeNode = pm.PyNode(blendShapeNode)

        # Get BSWeights attributes.
        # BlendShape node can have a lot of unused index, so we store the name of each element attribute,
        # to avoid possible errors.
        BSElements = blendShapeNode.weight.elements()  # list of unicode

        targetBShapes = []
        for attr in BSElements:
            targetBShapes.append(CopyDeforms.copyBlendShape(blendShapeNode.attr(attr), targetMesh))

        # create BlendShapeNode
        BlendShapeNode = pm.blendShape(targetBShapes, targetMesh)[0]
        # save blendShapeNames
        BSNames = [str(BSName) for BSName in targetBShapes]
        # delete Extracted BlendShapes, we don't need anymore
        pm.delete(targetBShapes)

        return BlendShapeNode, BSNames

    @staticmethod
    def copyClusterWeights(deformer, mesh):
        # documentation: https://groups.google.com/forum/#!topic/python_inside_maya/E7QirW4Z0Nw
        # documentation: https://help.autodesk.com/view/MAYAUL/2018/ENU/?guid=__cpp_ref_class_m_fn_set_html  # mfnSet
        # documentation: https://help.autodesk.com/view/MAYAUL/2018/ENU/?guid=__cpp_ref_class_m_fn_weight_geometry_filter_html  # geometryFilter
        """
        copy cluster weights between meshes
        :param deformer(str): cluster deformer name
        :param mesh2(str): mesh shape where copy weights
        :return:
        """
        # util
        util = OpenMaya.MScriptUtil()

        # get cluster
        mSelection = OpenMaya.MSelectionList()
        mSelection.add(deformer)
        mSelection.add(mesh)
        # deformer
        deformerMObject = OpenMaya.MObject()
        mSelection.getDependNode(0, deformerMObject)

        # weight mfn
        weightGeometryFilter = OpenMayaAnim.MFnWeightGeometryFilter(deformerMObject)
        membersSelList = OpenMaya.MSelectionList()
        fnSet = OpenMaya.MFnSet(weightGeometryFilter.deformerSet())  # set components affected
        fnSet.getMembers(membersSelList, False)  # add to selection list
        dagPathComponents = OpenMaya.MDagPath()
        components = OpenMaya.MObject()
        membersSelList.getDagPath(0, dagPathComponents, components)  # first element deformer set
        # get original weights
        originalWeight = OpenMaya.MFloatArray()
        weightGeometryFilter.getWeights(0, components, originalWeight)  # review documentation

        # get target mfn and all point positions
        targetDPath = OpenMaya.MDagPath()
        mSelection.getDagPath(1, targetDPath)
        if targetDPath.apiType() is OpenMaya.MFn.kTransform:
            targetDPath.extendToShape()  # if is ktransform type. get the shape
        # target It
        targetIt = OpenMaya.MItMeshVertex(targetDPath)

        # deformer vertex iterator
        sourceVertIt = OpenMaya.MItMeshVertex(dagPathComponents, components)
        sourceMFn = OpenMaya.MFnMesh(dagPathComponents)
        # list index on set fn
        sourceVertexId = OpenMaya.MIntArray()
        while not sourceVertIt.isDone():
            sourceVertexId.append(sourceVertIt.index())
            sourceVertIt.next()

        sourceVertIt.reset()
        logger.debug('source vertex id: %s' % sourceVertexId)

        targetDeformVId = OpenMaya.MIntArray()
        targetSelList = OpenMaya.MSelectionList()
        newWeights = OpenMaya.MFloatArray()
        lastLength = 0  # useful to find valid vertex
        # closest vertex from target to source
        # review, optimize
        while not targetIt.isDone():
            TVid = targetIt.index()
            TargetPoint = targetIt.position()
            closestPoint = OpenMaya.MPoint()
            ptr = util.asIntPtr()
            sourceMFn.getClosestPoint(TargetPoint, closestPoint, OpenMaya.MSpace.kObject, ptr)
            polyId = util.getInt(ptr)

            # get vertices from face id
            vertexId = OpenMaya.MIntArray()
            # gives the vertex in non clock direction
            sourceMFn.getPolygonVertices(polyId, vertexId)
            vertexLength = vertexId.length()
            weightList=[]
            totalArea = 0
            areaList=[]
            totalWeight = 0
            # polygonArea
            # sourceVertIt.setIndex(polyId)
            # iterate over the face vertex
            # check if any vertex is in the list of source vertex
            # TODO: review calculations, and try to optimize
            if set(vertexId) & set(sourceVertexId):
                for i, Vid in enumerate(vertexId):
                    # check first if any vertex is in the list
                    # calculate relative weight.
                    # get distance from vertex.
                    DistPoint = OpenMaya.MPoint()
                    sourceMFn.getPoint(Vid, DistPoint)  # get weighted vertex position
                    DistVector = OpenMaya.MVector(closestPoint - DistPoint)
                    vectorA = OpenMaya.MPoint()  # vectorA
                    sourceMFn.getPoint(vertexId[i-1], vectorA)
                    vectorB = OpenMaya.MPoint()  # vertorB
                    sourceMFn.getPoint(vertexId[(i+1) % vertexLength], vectorB)
                    # contruct baricentric vectors
                    # documentation: http://blackpawn.com/texts/pointinpoly/
                    vectorA = OpenMaya.MVector(vectorA - DistPoint)
                    vectorB = OpenMaya.MVector(vectorB - DistPoint)
                    #denominator
                    denom = ((vectorA*vectorA)*(vectorB*vectorB)-(vectorA*vectorB)*(vectorB*vectorA))
                    # u and V
                    u = ((vectorB*vectorB)*(DistVector*vectorA)-(vectorB*vectorA)*(DistVector*vectorB))/denom
                    v = ((vectorA*vectorA)*(DistVector*vectorB)-(vectorA*vectorB)*(DistVector*vectorA))/denom
                    areaVector = (vectorA*(1-u) ^ vectorB*(1-v)).length()
                    totalArea += areaVector
                    areaList.append(areaVector)

                    # get wheights
                    if Vid in sourceVertexId:
                        weightIndex = list(sourceVertexId).index(Vid)  # get the vertex list index, valid for the weight list
                        sourceWeight = originalWeight[weightIndex]  # get weight value from the list
                    else:
                        sourceWeight = 0
                    weightList.append(sourceWeight)

                    # save valid vertex index. only once.
                    if not TVid in targetDeformVId:
                        targetDeformVId.append(TVid)
                        # save components in a selection list. this way we can add it to our set
                        targetSelList.add(targetDPath, targetIt.currentItem())

            # now calculate and assign weight value
            newLength = targetDeformVId.length()
            if lastLength < newLength:
                weightTarget = 0
                for i, area in enumerate(areaList):
                    weightTarget += (area/totalArea)*weightList[i]

                newWeights.append(weightTarget)
                lastLength = newLength

            targetIt.next()

        # add to mfnSet
        fnSet.addMembers(targetSelList)
        PaintSelList = OpenMaya.MSelectionList()
        fnSet.getMembers(PaintSelList, False)

        # calculate weights
        # get from selection list
        components = OpenMaya.MObject()
        targetNewWDPath = OpenMaya.MDagPath()
        for i in range(PaintSelList.length()):
            # check we have desired dagpath
            PaintSelList.getDagPath(i, targetNewWDPath, components)
            if targetNewWDPath.partialPathName() == targetDPath.partialPathName():
                break
        print newWeights
        weightGeometryFilter.setWeight(targetNewWDPath, components, newWeights)


class PickerTools(object):
    @staticmethod
    def addPickerAttribute(attribute='picker', expression='pass'):
        selection = cmds.ls(sl=True)
        for sel in selection:
            if not cmds.attributeQuery(attribute, node=sel):
                cmds.addAttr(sel, longName=attribute, shortName=attribute, dt='string')

            cmds.setAttr('%s.%s' % (sel, attribute), expression, type='string')

    ## copy colors ##
    @staticmethod
    def copyShapeColor():
        selection = cmds.ls(sl=True)
        colorObject = selection[0]
        shape = cmds.listRelatives(colorObject, s=True)[0]
        color = cmds.getAttr('%s.overrideColorRGB' % shape)[0]
        print color

        for sel in selection[1:]:
            selShape = cmds.listRelatives(sel, s=True)[0]
            print selShape
            cmds.setAttr('%s.overrideColorRGB' % selShape, *color)