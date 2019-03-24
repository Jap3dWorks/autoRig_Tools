import pymel.core as pm
from maya import OpenMaya
import re
import math
from maya import mel

from _autoRig_Abstract import _ARAutoRig_Abstract
from ..ARCore import ARCore as ARC

import logging

logging.basicConfig()
logger = logging.getLogger('ARAutoRig_Face:')
logger.setLevel(logging.DEBUG)


class ARAutoRig_Face(_ARAutoRig_Abstract):
    """
    Class to construct facial rig
    """

    def __init__(self, chName, path, meshShape):
        self.controllers = {}  # dict with controllers created
        self.sysObj = {}  # dict with interest sys obj, sometimes it 's helpful to add extra functions
        self.autoSDK_grps = {}  # grps autos SDK

        meshShape = pm.PyNode(meshShape) if isinstance(meshShape, str) else meshShape
        meshShape = meshShape.getShape if isinstance(meshShape, pm.nodetypes.Transform) else meshShape
        self._MESH_SHAPE = meshShape

        # util attributes
        self._baseName = ""

        super(ARAutoRig_Face, self).__init__(chName, path)


    def wires_auto(self, deformer, parent=None, sizeCtr=0.5, customCtr=None, ctrFollow=False, orientType=None):
        """
        This method configure a wire deform for facial rigs.
        The wire must be created and painted previously.
        :param deformer:
        :param orientPlane(str): zx, xy, etc. align the orient matrix of the controller with the plane,
        "mesh", orient to mesh nearest normal
        :param :
        :return:

        self.controllers: store controllers
        self.sysObj: store planes (mesh) that drive the auto grps
        """
        deformer = pm.PyNode(deformer) if isinstance(deformer, str) else deformer

        # base name
        self._baseName = str(deformer).split("_")[:-2]
        self._baseName = "_".join(self._baseName)

        # if no parent, create a empty grp to use
        if not parent:
            parent = pm.group(empty=True, name="%s_grp" % self._baseName)
            self._ctrGrp.addChild(parent)

        curveBaseW = deformer.baseWire.inputs(p=True)[0].node()
        curve = deformer.deformedWire.inputs(p=True)[0].node()

        # parent the curves to no xform grp
        self._noXformGrp.addChild(curve)
        self._noXformGrp.addChild(curveBaseW)

        # create driver groups
        # create transforms to drive the curve
        controllers = ARC.transformDriveNurbObjectCV(curve, ctrFollow)
        baseCurveGrps = ARC.transformDriveNurbObjectCV(curveBaseW, ctrFollow)
        if ctrFollow:
            for i in range(len(controllers)):
                # align matrix
                matrix = controllers[i].getMatrix()
                if orientType:
                    if orientType == "mesh":
                        normal = self._MESH_SHAPE.getClosestNormal(matrix[3][:3], "world")[0]
                        matrix = ARC.VectorMath.orientMatrixToVector(matrix, normal, "y")
                    else:
                        matrix = ARC.VectorMath.orientMatrixToPlane(matrix, orientType)
                if matrix[3][0] < 0:
                    matrix[0] = matrix[0] * -1

                controllers[i].setMatrix(matrix)
                baseCurveGrps[i].setMatrix(matrix)
                logger.debug("align to plane")

        # parent controllers
        pm.parent(controllers, parent)
        pm.parent(baseCurveGrps, self._noXformGrp)

        self.addShapeCtr(controllers, sizeCtr, customCtr)

        ARC.createRoots(controllers, "root")
        auto = ARC.createRoots(controllers, "auto")
        autoSDK = ARC.createRoots(controllers, "autoSDK")

        planes = self._deformPlanes(auto, baseCurveGrps)

        # save data
        self.controllers[self._baseName] = controllers
        self.sysObj[self._baseName] = planes
        self.autoSDK_grps[self._baseName] = autoSDK
        self.last_autoSDK = autoSDK


    def auto_SDK(self, symAxis="x", midCtr = True, log=False):
        """
        create auto sdk
        :return:
        """
        VMN = ARC.VectorMath_Nodes
        axisList = "XYZ"

        # get two possible sides
        positive=list(self.last_autoSDK)
        positive.sort(key=ARC.sortByPosition)
        negative=list(self.last_autoSDK)
        negative.sort(key=ARC.sortByPosition, reverse=True)

        listLen = len(positive)

        logger.debug("Positive list: %s" % positive)
        logger.debug("Negative list: %s" % negative)

        if midCtr:
            listOptions = [positive, negative, positive[:listLen/2+1], negative[:listLen/2+1]]
        else:
            listOptions = [positive, negative]


        for op, side in enumerate(listOptions):
            if not side:
                continue
            driver = [d for d in side[-1].getChildren() if isinstance(d, pm.nodetypes.Transform)][0]
            lenSide = float(len(side))

            influence = lambda x: x / lenSide  # influence formula

            if log:
                # influence = lambda x: math.log( len(side), x) if x != 0 else 0
                if op <2:
                    # influence = lambda x: (x / lenSide) ** 2.0
                    # influence = lambda x: math.sqrt(x / lenSide)
                    influence = lambda x: x / lenSide  # influence formula

                else:
                    print "op %s" % op
                    influence = lambda x: (x / lenSide) ** (1/2.5)

            driverMatrix = pm.xform(driver, q=True, ws=True, m=True)
            for i, obj in enumerate(side[:-1]):
                autoMatrix = pm.xform(obj, q=True, ws=True, m=True)

                # create anim nodes for each attribute
                for attr in ["translate"]:
                    for j, axis in enumerate(axisList):
                        # additive for functions
                        logger.debug("Current axis SDK: %s, %s" % (axis, j))
                        # each attribute has its animCurve type
                        animNode = pm.createNode("animCurveTL") if attr == "translate" else pm.createNode("animCurveTA")  # create anim node
                        driver.attr("%s%s" % (attr, axis)).connect(animNode.input)
                        plugs = obj.attr("%s%s" % (attr, axis)).inputs(p=True)

                        if plugs:
                            logger.debug("Found plugs: %s" % plugs)
                            plugs[0].disconnect(obj.attr("%s%s" % (attr, axis)))
                            plusNode = VMN.plusMinusAverage(1, plugs[0], animNode.output)
                            plusNode.connect(obj.attr("%s%s" % (attr, axis)))
                        else:
                            animNode.output.connect(obj.attr("%s%s" % (attr, axis)))

                        # todo: ARC function for driven keys
                        drvVector = pm.datatypes.Vector(driverMatrix[j])
                        autoVector = pm.datatypes.Vector(autoMatrix[j])
                        dot = drvVector * autoVector
                        logger.debug("dot: %s" %(dot))
                        dot = dot if dot != 0 else 1
                        sign = dot/abs(dot)
                        logger.debug("sign:%s" %(sign))
                        print influence(i)
                        print i
                        print i/len(side)
                        print len(side)

                        animNode.addKeyframe(0, 0.0)
                        animNode.addKeyframe(1, influence(i)*sign)
                        animNode.addKeyframe(-1, -(influence(i)*sign))

                        animNode.setTangentTypes([0, 1, 2], inTangentType='linear', outTangentType='linear')
                        animNode.setTangentTypes([0, 2], inTangentType='clamped', outTangentType='clamped')

                        animNode.setPostInfinityType('linear')
                        animNode.setPreInfinityType('linear')



    def addCluster(self, clsTrns, parent=None, ctrSize=1.0, ctrlNull=None, symCtr=False, mirrorCls=False):
        """
        create a cluster for facial rigs
        :param clsTrns:
        :param parent:
        :param ctrType:
        :param ctrSize:
        :param ctrlNull: null where controller will be moved
        :param symCtr: inverse matrix transform of the controller
        :param mirrorCls: create a new mirrored cluster
        :return:
        """
        # check type
        clsTrns = pm.PyNode(clsTrns) if isinstance(clsTrns, str) else clsTrns

        self._baseName = str(clsTrns).split("_")[:-2]
        self._baseName = "_".join(self._baseName)
        # replace left right
        if mirrorCls:
            if "left" in self._baseName:
                self._baseName = self._baseName.replace("left", "right")
            else:
                self._baseName = self._baseName.replace("right", "left")

        # if no parent, create a empty grp to use
        if not parent:
            parent = pm.group(empty=True, name="%s_def_cls_grp" % self._baseName)
            self._ctrGrp.addChild(parent)

        if mirrorCls:  # fixme delete
            clsNode = clsTrns.worldMatrix.outputs(type="cluster")[0]
            clsNode, clsTrns, clsShape = ARC.DeformerOp.mirrorCluster(clsNode)
            clsTrns.rename(self._baseName + "_def_cls")
            clsNode.rename(self._baseName + "_def_cls_cls")

        clusterCtr = super(ARAutoRig_Face, self).addCluster(clsTrns, parent, "pole", ctrSize, ctrlNull, symCtr)[0]

        clusterCtr = clusterCtr[0]
        self.addShapeCtr(clusterCtr, ctrSize, None)

        clsAuto = pm.group(empty=True, name="%s_auto" % str(clsTrns))
        clsAuto.setTranslation(clsTrns.getPivots(ws=True)[0], "world")
        parent.addChild(clsAuto)
        clsAuto.addChild(clsTrns.firstParent())

        # create planes to drive clusters
        autoGrp = ARC.createRoots(clusterCtr.firstParent(), "auto")
        planes = self._deformPlanes(autoGrp, [clsAuto])

        # save data
        self.controllers[self._baseName] = clusterCtr
        self.sysObj[self._baseName] = planes


    def cloneJointsCtr(self, root):
        """
        Clone Joints, and set as controllers
        :param root: root joint
        :return:
        """
        controllers, joints = ARC.cloneWithHierarchy(root, "joint", "ctr")
        logger.debug(controllers)
        valControllers = []
        valJoints = []
        # get only valid joints
        for i in range(len(joints)):
            if "End" in str(joints[i]) or "Tip" in str(joints[i]):
                pm.delete(controllers[i])

            elif isinstance(joints[i], pm.nodetypes.Joint):
                valControllers.append(controllers[i])
                valJoints.append(joints[i])

        logger.debug("%s, %s" %(len(valControllers), len(valJoints)))

        # root and autos
        controllersRoot = ARC.createRoots(valControllers, "root")
        controllersAuto = ARC.createRoots(valControllers, "auto")

        # parent constraint and type of visualization
        for i in range(len(valJoints)):
            valControllers[i].drawStyle.set(2)
            valControllers[i].displayHandle.set(True)

            pm.parentConstraint(valControllers[i], valJoints[i], maintainOffset=True)


        self.controllers["jointControllers"] = valControllers


    def _deformPlanes(self, autoGrp, baseGrp=None):
        """
        Create a plane and copy the deforms from base mesh, then constraint the autoGrp and baseGrp to the plane
        :param autoGrp:autoGrp, generally contains a controller as child
        :param baseGrp: to control a baseShape like wire deformer baseCure
        :return: planes
        """
        # create a small plane per point, then combine them
        planes = []
        for ctr in autoGrp:
            plane = pm.polyPlane(h=0.01, w=0.01, sh=1, sw=1, ch=False)[0]
            plane.setTranslation(ctr.getTranslation("world"), "world")
            planes.append(plane)

        # combine planes
        if len(planes) > 1:
            # len 1 gives an error with polyUnite
            planes = pm.polyUnite(planes, ch=False, mergeUVSets=True)[0]
        else:
            planes = planes[0]
            pm.makeIdentity(planes, a=True, r=True, s=True, t=True)
            planes.setPivots([0, 0, 0])

        planes.rename("%s_planes" % self._baseName)  # rename
        pm.polyAutoProjection(planes, ch=False, lm=0, pb=0, ibd=1, cm=0, l=2, sc=1, o=1, p=6, ps=0.2, ws=0)  # uvs

        if self._MESH_SHAPE:
            # if skin sample, copy skin weights to planes
            # find skin node
            skinNode = pm.listHistory(self._MESH_SHAPE, type='skinCluster')[0]
            # joint list
            jointList = skinNode.influenceObjects()
            # create skinCluster
            copySkinCluster = pm.skinCluster(planes, jointList, mi=3)
            # copy skin weigths
            pm.copySkinWeights(ss=skinNode, ds=copySkinCluster, noMirror=True, surfaceAssociation='closestPoint',
                               influenceAssociation=('closestJoint', 'closestJoint'))


        # connect each auto grp to each poly face
        numFaces = planes.getShape().numFaces()
        logger.debug("num Faces: %s" % numFaces)
        for i in range(numFaces):
            pm.select(planes.f[i], r=True)
            pm.select(autoGrp[i], add=True)
            pm.pointOnPolyConstraint(maintainOffset=True)
            pm.select(cl=True)
            if baseGrp:
                pm.select(planes.f[i], r=True)
                pm.select(baseGrp[i], add=True)
                pm.pointOnPolyConstraint(maintainOffset=True)
                pm.select(cl=True)

            #hammer weights
            try:
                #TODO: bad aproximation
                vertex = pm.modeling.polyListComponentConversion(planes.f[i], tv=True)
                pm.select(vertex, r=True)
                logger.debug("vertices %s:" % vertex)
                mel.eval("weightHammerVerts;")
                pm.select(cl=True)
            except:
                pm.select(cl=True)



        # parent planes to nonXform grp
        self._noXformGrp.addChild(planes)  # parent to noXform
        return planes