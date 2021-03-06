# tools for use the rig

import maya.cmds as cmds
from maya import OpenMaya
from maya import OpenMayaAnim
import maya.mel as mel
import re
import pymel.core as pm
import math
from ..ARCore import ARCore as ARC  # relative path ..

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
        # check types
        positive = pm.PyNode(positive) if isinstance(positive, str) else positive
        positive = positive.getShape() if isinstance(positive, pm.nodetypes.Transform) else positive
        negative = pm.PyNode(negative) if isinstance(negative, str) else negative
        negative = negative.getShape() if isinstance(negative, pm.nodetypes.Transform) else negative
        base = pm.PyNode(base) if isinstance(base, str) else base
        base = base.getShape() if isinstance(base, pm.nodetypes.Transform) else base


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
    def getDeltaByJointAngle(positive, skinMesh,  joint):
        """
        # TODO: optimize
        FIXME: seems that the system left a litle range of angle.
        tested with matrix transform and there is the same problem.
        it is possible some joint data are getting bad results?
        Extract a delta from a sculpted position mesh, more precise method
        positive(pm.mesh): posed sculpted mesh
        skinMesh(pm.mesh): skined mesh, posed like sculpted mesh. be careful with the input nodes, the skin cluster may be accessible
        joint(pm.Joint): joint rotated for the pose
        """
        toApiQ = lambda x: OpenMaya.MQuaternion(x)

        # check types
        positive = pm.PyNode(positive) if isinstance(positive, str) else positive
        skinMesh = pm.PyNode(skinMesh) if isinstance(skinMesh, str) else skinMesh
        skinMesh = skinMesh.getShape() if isinstance(skinMesh, pm.nodetypes.Transform) else skinMesh
        joint = pm.PyNode(joint) if isinstance(joint, str) else joint

        # get diferences
        diferenceIndex = []
        for i, point in enumerate(positive.getPoints('object')):
            if point != skinMesh.getPoint(i, 'object'):
                diferenceIndex.append(i)

        skinCluster = skinMesh.listConnections(connections=True, type='skinCluster')[0][1]
        skinCluster = pm.PyNode(skinCluster)  # convert to pyNode

        # query angles
        worldQ = toApiQ(joint.getRotation(quaternion=True, space='world'))
        # get joint angle
        angleEu = joint.getRotation()
        # set to zero, to query the quaternion value
        joint.setRotation([0, 0, 0])
        zeroQ = toApiQ(joint.getRotation(quaternion=True, space='world'))

        offsetQ = zeroQ.invertIt() * worldQ  # final quaternion  angle

        rotAxis = OpenMaya.MVector()
        util = OpenMaya.MScriptUtil()
        ptr = util.asDoublePtr()
        offsetQ.getAxisAngle(rotAxis, ptr)  # <- get angle and vector
        angle = util.getDouble(ptr)

        # joint position
        jointPos = joint.getTranslation('world')

        # create base pose
        baseMesh = skinMesh.duplicate(name='%s_delta' % str(skinMesh))[0]
        baseMeshShape = baseMesh.getShape()

        #space locator
        loc = pm.spaceLocator()
        loc.setTranslation(rotAxis * 5)

        # TODO: vertex no modified get from skinned mesh joint pos == 0
        for index in diferenceIndex:
            influence = pm.skinPercent(skinCluster, skinMesh.vtx[index], transform=joint, query=True)
            # influence plus influences of child joints
            joinChild = [str(j) for j in joint.listRelatives(ad=True)]
            jointsInfluence = pm.skinPercent(skinCluster, skinMesh.vtx[index], q=True, transform=None)
            matchJoint = set(joinChild).intersection(set(jointsInfluence))
            for j in matchJoint:
                influence += pm.skinPercent(skinCluster, skinMesh.vtx[index], transform=j, query=True)

            # vector from joint to vertex sculpted
            sculptVector = positive.getPoint(index, 'object')  # review
            sculptVector = pm.datatypes.Vector(sculptVector - jointPos)

            # if influence == 0 don't calculate
            if influence:
                angleA = math.pi - (angle/2 + math.pi/2)
                angleB = math.pi - (angle*influence + angleA)
                # with sin rules get the length of final vector
                lengthFVector = sculptVector.length()*math.sin(angleB)/math.sin(angleA)
                # create relative quaternion to influence
                qAngl = - (angle * influence)
                relativeQ = OpenMaya.MQuaternion(qAngl, rotAxis)

                rotatedVector = sculptVector.rotateBy(relativeQ)
                rotatedVector.normalize()
                rotatedVector = rotatedVector*lengthFVector  # correct length

                sculptVector = rotatedVector

            baseMeshShape.setPoint(index, sculptVector + jointPos, 'world')

        joint.setRotation(angleEu)


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
        disconnect a blend shape, connect a mesh with a wrap then clone that mesh
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
    def addToDeformer_Tool(deformer, mesh):
        ARC.DeformerOp.addToDeformer(deformer, mesh)
"""
--Example Copy deformers--

# copy skin
rigTools.CopyDeforms.copySkin('akona_body_mesh', 'akona_cloths_deformMesh')

# copy BS
rigTools.CopyDeforms.copyBlendShapes('PSDAkona', 'akona_cloths_deformMesh')

# connect BS to PSD
rigTools.PSDUtils.connectBlendShapes('akona_PSDCloth')

# connect Clusters
rigTools.CopyDeforms.copyClusterWeights('cluster1', 'pTorus1')
# rigTools.CopyDeforms.copyClusterWeights('akona_chest_clusterCluster', 'akona_cloths_deformMesh')


# move skinedjoints
cmds.skinCluster('akona_cloths_deformMesh', e=True, mjm=False)
cmds.skinCluster('skinHelper', e=True, mjm=False)
cmds.skinCluster('akona_hair_mesh', e=True, mjm=False)
"""


def variableFkTool(curve, numJoints, numControllers=3):
    """
    Given a curve, set up a variable fk system.
    :param curve(str or pm): guide curve
    :param numJoints (int): num of joints for the system
    :param numControllers (int): FK controllers per system
    :return:
    """
    # check data type
    if isinstance(curve, str):
        curve = pm.PyNode(curve)
    if isinstance(curve, pm.nodetypes.Transform):
        curve = curve.getShape()

    # create joint chain
    joints = ARC.jointChain(None, numJoints, curve)

    ARC.variableFk(joints, curve, numControllers)


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
            print selShape + " RGB"
            cmds.setAttr('%s.overrideEnabled' % selShape, True)
            cmds.setAttr('%s.overrideRGBColors' % selShape, 1)
            cmds.setAttr('%s.overrideColorRGB' % selShape, *color)

    # buttons dictionary
    @staticmethod
    def getControllerButtons():
        """
        {controllerName:[[position],[size]], ... }
        :return (dict): controllers
        """
        normalizeValue = 12.0
        meshes = cmds.ls(type='mesh')
        controllers = {}

        # get controller info
        for mesh in meshes:
            meshInfo = []
            # get transform
            transform = cmds.listRelatives(mesh, p=True)[0]
            # position
            bbox = cmds.xform(transform, boundingBox=True, ws=True, q=True)
            position = [bbox[0] / normalizeValue, bbox[2] / normalizeValue]
            meshInfo.append(position)

            # calculate size
            size = [math.fabs((bbox[3] - bbox[0]) / normalizeValue), math.fabs((bbox[2] - bbox[5]) / normalizeValue)]
            meshInfo.append(size)

            # color
            color = cmds.getAttr('%s.overrideColorRGB' % mesh)[0]
            meshInfo.append(color)

            # extra attributes
            for attr in ('ikFk', 'snap'):
                attrValue = cmds.getAttr('%s.%s' % (transform, attr))
                meshInfo.append(attrValue)

            # save controller to dictionary
            controllers[transform] = meshInfo

        return controllers


#########################
##Shape Modelling Tools##
#########################
class MirrorControllers(object):
    """
    Tools for shapes modeling with controllers.
    """
    def __init__(self, axis=(-1,1,1)):
        """
        need a zero position frame
        """
        self.axis = axis
        selection = pm.ls(sl=True)
        # find symetry controllers from selection
        self.symetryControls, self.noSymetryControls = ARC.findMirrorPoints(selection, axis)

        logger.info('Mirror Controllers store')


    def mirror(self, worldSpace=False, symetrize= False):
        """
        mirror the controllers position and orientation
        :return:
        """
        flippedAxis = 'xyz'
        flippedVector = None
        # create reflection Matrix
        reflMatrix = pm.datatypes.Matrix()
        for i in range(len(self.axis)):
            reflMatrix[i] *= self.axis[i]
            # only flip 1 axis
            if self.axis[i] < 0:
                # get flipped axis
                flippedVector = i
                flippedAxis = flippedAxis[i]
                break
        else:
            logger.info('No flipped axis, please add a flipped axis p.e(-1,1,1)')
            return

        if not symetrize:
            # inver positions
            for pairCtr in self.symetryControls:
                matrix1 = pm.xform(pairCtr[0], ws=worldSpace, q=True, m=True)
                matrix1 = ARC.checkMatrixType(matrix1)
                invMatrix1 = ARC.VectorMath.reflectedMatrix(matrix1, reflMatrix)

                matrix2 = pm.xform(pairCtr[1], ws=worldSpace, q=True, m=True)
                matrix2 = ARC.checkMatrixType(matrix2)
                invMatrix2 = ARC.VectorMath.reflectedMatrix(matrix2, reflMatrix)

                # apply matrix
                pm.xform(pairCtr[0], ws=worldSpace, m=invMatrix2)
                pm.xform(pairCtr[1], ws=worldSpace, m=invMatrix1)

            for ctr in self.noSymetryControls:
                matrix = pm.xform(ctr, ws=worldSpace, q=True, m=True)
                invMatrix = ARC.VectorMath.reflectedMatrix(matrix, reflMatrix)
                # apply
                pm.xform(ctr, ws=worldSpace, m=invMatrix)

            logger.info('Mirror done')

        # symmetrize
        else:
            for pairCtr in self.symetryControls:
                positiveIndex = 0 if getattr(pairCtr[0].getTranslation('world'), '%s' % flippedAxis) > 0 else 1
                negativeIndex = 1 - positiveIndex

                matrixPositive = pm.xform(pairCtr[positiveIndex], ws=worldSpace, q=True, m=True)
                flipMatrix = ARC.VectorMath.reflectedMatrix(matrixPositive, reflMatrix)

                # apply matrix
                pm.xform(pairCtr[negativeIndex], ws=worldSpace, m=flipMatrix)

            logger.info('Symmetry done')


def dupGeoEachFrame(mesh, animatedAttr):
    """
    Clone the given mesh each animatedAttr frame
    :param mesh:
    :param animatedObj:
    :return:
    """
    # data types
    if isinstance(mesh, str):
        mesh = pm.PyNode(mesh)
    if not isinstance(mesh, pm.nodetypes.Transform):
        mesh = mesh.getTransform()

    # animated obj
    if isinstance(animatedAttr, str):
        animatedAttr = pm.PyNode(animatedAttr)
    if not isinstance(animatedAttr, pm.general.Attribute):
        logger.info('animatedAttr must be an attribute')
        return

    animNode = animatedAttr.inputs(type='animCurve')[0]
    if not animNode:
        logger.info('%s has not animation' % animatedAttr)
        return

    KeyFrames = [animNode.getTime(i) for i in range(animNode.numKeys())]

    dupGrp = pm.group(empty=True, name=str(mesh)+'_dups')
    dupMeshes =[]
    for frame in KeyFrames:
        # set Time at frame
        pm.currentTime(frame, edit=True)
        # clone the mesh
        dupMeshes.append(mesh.duplicate(name=str(mesh)+'f%s' % frame)[0])
        dupGrp.addChild(dupMeshes[-1])

    return dupMeshes





