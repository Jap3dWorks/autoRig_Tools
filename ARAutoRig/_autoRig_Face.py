import pymel.core as pm
from maya import OpenMaya
import re

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
    def __init__(self, chName, path):
        self.controllers = {}

        super(ARAutoRig_Face, self).__init__(chName, path)


    def wires_auto(self, deformer, skinSample=None, parent=None, sizeCtr=0.5, customCtr=None):
        """
        This method configure a wire deform for facial rigs.
        The wire must be created and painted previously.
        :param deformer:
        :param skinSample: mesh with a skin cluster, TODO: get shample from deformer too
        :param :
        :return:
        """
        deformer = pm.PyNode(deformer) if isinstance(deformer, str) else deformer

        # base name
        baseName = str(deformer).split("_")[:-2]
        baseName = "_".join(baseName)
        print baseName

        # if no parent, create a empty grp to use
        if not parent:
            parent = pm.group(empty=True, name="%s_grp" % baseName)
            self._ctrGrp.addChild(parent)

        curveBaseW = deformer.baseWire.inputs(p=True)[0].node()
        curve = deformer.deformedWire.inputs(p=True)[0].node()


        # parent the curves to no xform grp
        self._noXformGrp.addChild(curve)
        self._noXformGrp.addChild(curveBaseW)

        # create driver groups
        # create transforms to drive the curve
        controllers = ARC.transformDriveNurbObjectCV(curve)
        baseCurveGrps=ARC.transformDriveNurbObjectCV(curveBaseW)

        # parent controllers
        pm.parent(controllers, parent)
        pm.parent(baseCurveGrps, self._noXformGrp)
        # controller shape
        for ctr in controllers:
            sphere = pm.sphere(r=sizeCtr, ch=False)[0]
            ctr.addChild(sphere.getShape(), r=True, s=True)
            pm.delete(sphere)

        # roots and auto grps
        ARC.createRoots(controllers, "root")
        auto = ARC.createRoots(controllers, "auto")

        # create a small plane per point, then combine them
        planes=[]
        for ctr in controllers:
            plane = pm.polyPlane(h=0.01, w=0.01, sh=1, sw=1, ch=False)[0]
            plane.setTranslation(ctr.getTranslation("world"), "world")
            planes.append(plane)

        # combine planes
        planes = pm.polyUnite(planes, ch=False, mergeUVSets=True)[0]
        planes.rename("%s_planes" % baseName)
        self._noXformGrp.addChild(planes)  # save to noXform
        pm.polyAutoProjection(planes, ch=False, lm=0, pb=0, ibd=1, cm=0, l=2, sc=1, o=1, p=6, ps=0.2, ws=0)

        if skinSample:
            # if skin sample, copy skin weights to planes
            if isinstance(skinSample, str):
                skinSample = pm.PyNode(skinSample)
            if isinstance(skinSample, pm.nodetypes.Transform):
                skinSample = skinSample.getShape()
            # find skin node
            skinNode = pm.listHistory(skinSample, type='skinCluster')[0]
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
            # review: don't know why, only works with selection
            for constr in [auto[i], baseCurveGrps[i]]:
                pm.select(planes.f[i], r=True)
                pm.select(constr, add=True)
                pm.pointOnPolyConstraint(maintainOffset=True)
                pm.select(cl=True)

        # save data
        self.controllers[baseName]=controllers
