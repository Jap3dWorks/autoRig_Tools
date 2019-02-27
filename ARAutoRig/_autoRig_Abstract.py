import pymel.core as pm
import re
from maya import OpenMaya

from ..ARCore import ARCore as ARC

import logging
logging.basicConfig()
logger = logging.getLogger('ARAutoRig_Abstract:')
logger.setLevel(logging.DEBUG)

class _ARAutoRig_Abstract(object):
    def __init__(self, chName, path):
        """
        autoRig class tools
        """
        # TODO: create node Module or chName_rig_grp transform node with messages attributes to store connections
        self._chName = chName
        self._path = path

        # private attributes
        self._lastZone=""
        self._lastSide=""
        # skin joints name marker
        self._skinJointNaming = "skin_joint"

        # create necessary groups
        # check if noXform exist
        try:
            self._noXformGrp = pm.PyNode('noXform_grp')
        except:
            self._noXformGrp = pm.group(name='noXform_grp', empty=True)
            self._noXformGrp.inheritsTransform.set(False)
            pm.PyNode('rig_grp').addChild(self._noXformGrp)

        # check if ctr_grp exist
        try:
            self._ctrGrp = pm.PyNode('ctr_grp')
        except:
            self._ctrGrp = pm.group(name='ctr_grp', empty=True)
            pm.PyNode('rig_grp').addChild(self._ctrGrp)



    # method decorator, check if already exist the rig part,
    # and create the necessary attr circuity (nodes with controllers connections)
    class checker_auto(object):
        def __init__(self, decorated):
            # TODO: do not understand why i need to make this
            self._decorated = decorated

        def __call__(self, func):
            # store func name
            # here we have the zone defined
            funcName = func.__name__.replace('_auto', '')

            # start wrapper
            def wrapper(*args, **kwargs):
                # check if node exist
                # check if side is in args
                chName = args[0].chName  # explanation: acces outher class attributes
                sideCheck = 'left' if 'left' in args else 'right' if 'right' in args else None
                sideCheck = kwargs['side'] if 'side' in kwargs else sideCheck

                moduleSide = '%s_module' % sideCheck if sideCheck else 'module'
                nodeName = '%s_%s_%s' % (chName, funcName, moduleSide)  # name of the desired node
                # check if module allready exists
                try:
                    moduleNode = pm.PyNode(nodeName)
                except:
                    moduleNode = None

                if moduleNode:
                    logger.debug('%s %s module exist yet' % (nodeName))
                    return None

                # if module does not exist, run method
                # also get info to construct the necessary nodes
                totalControlList = func(*args, **kwargs)

                # create unknown node
                connectionTypes = ['ikControllers', 'fkControllers']
                moduleNode = pm.createNode('script', name=nodeName)
                pm.addAttr(moduleNode, ln='module', sn='module', attributeType='message')
                for connection in connectionTypes:
                    pm.addAttr(moduleNode, ln=connection, sn=connection, attributeType='message')

                for i, ctrType in enumerate(connectionTypes):
                    for ctr in totalControlList[i]:
                        pm.addAttr(ctr, ln='module', sn='module', attributeType='message')
                        moduleNode.attr(ctrType).connect(ctr.module)

                # connect to parent module
                # if not exist yet, create
                try:
                    chModule = pm.PyNode('%s' % chName)
                except:
                    raise ValueError('Do not found %s elements' % chName)

                # check connections
                if not chModule.hasAttr(funcName):
                    pm.addAttr(chModule, ln=funcName, sn=funcName, attributeType='message')

                chModule.attr(funcName).connect(moduleNode.module)

                return totalControlList

            return wrapper


    def latticeBend_auto(self, lattice, parent):
        """
        Given a lattice, create a bend deformer and connect it to the rig
        :param lattice (str or pm): lattice transform node or shape
        :param parent (str or pm):
        :return:
        """
        # check data type
        # check lattice type data
        if isinstance(lattice, str):
            lattice = pm.PyNode(lattice)
        if isinstance(lattice, pm.nodetypes.Transform):
            latticeTransform = lattice
            lattice = lattice.getShape()

        if isinstance(parent, str):
            parent = pm.PyNode(parent)

        # lattice nodes
        ffd = lattice.worldMatrix.outputs()[0]
        logger.debug('ffd1: %s' % ffd)
        latticeBase = ffd.baseLatticeMatrix.inputs()[0]
        logger.debug('latticeBase %s' % latticeBase)

        # look if lastSide attr exist
        baseName = [self._chName, self._lastZone]
        if hasattr(self, 'lastSide'):
            # if it is the case, append to name
            baseName.append(self._lastSide)

        baseName.extend(['lattice', 'ctr'])
        controllerName = '_'.join(baseName)

        controller = self._create_controller(controllerName, 'pole', 1.8, 24)
        latticeList = ARC.DeformerOp.latticeBendDeformer(lattice, controller)

        # parent
        latticeList.append(latticeBase)
        pm.parent(latticeList, parent)

        # hide lattice
        latticeTransform.visibility.set(False)

        return [], []


    def addCluster(self, cluster, parent, controllerType, controllerSize=1.0):
        """
        Take a cluster or create it, move it to the controller system, create a controller and vinculate
        :arg: cluster(str or pm): name of the cluster transform node
        :return:
        """
        # cluster var type
        if isinstance(cluster, str):
            cluster = pm.PyNode(cluster)
        # parent var type
        if isinstance(parent, str):
            parent = pm.PyNode(parent)

        clusterMatrix = pm.xform(cluster, ws=True, m=True, q=True)

        # look for cluster root
        clusterRoot = cluster.getParent()
        # check if parent is a root.
        if clusterRoot:
            rootMatrix = pm.xform(clusterRoot, ws=True, m=True, q=True)
            if rootMatrix == clusterMatrix and len(clusterRoot.listRelatives(c=True)) == 1:
                pass
            else:
                clusterRoot = ARC.createRoots([cluster])
        else:
            clusterRoot = ARC.createRoots([cluster])

        # look if cluster is relative
        # we need cluster DGnode
        clusterShape = cluster.getShape()
        clusterDG = clusterShape.clusterTransforms[0].outputs()[0]
        clusterDG.relative.set(True)

        # visibility shape
        clusterShape.visibility.set(False)

        # parent cluster root
        parent.addChild(clusterRoot)

        # createController
        controller = self._create_controller('%s_ctr' % str(cluster), controllerType, controllerSize, 24)
        # align with cluster, we need to query world space pivot
        controller.setTranslation(cluster.getPivots(ws=True)[0], 'world')
        #pm.xform(controller, ws=True, m=clusterMatrix)
        #parent
        parent.addChild(controller)
        # create root
        controllerRoot = ARC.createRoots([controller])

        # connect controllr and cluster
        pm.parentConstraint(controller, cluster, maintainOffset=False, name='%s_parentConstraint' % str(cluster))
        ARC.DGUtils.connectAttributes(controller, cluster, ['scale'], 'XYZ')

        return [controller], []


    def point_auto(self, zone, parent):
        """
        Create a simple point control for a joint
        :param zone: zone of the points (joints)
        :param parent: parent of the controllers
        :return:
        """
        pointJoints = [point for point in pm.ls() if re.match('^%s.*%s$' % (zone, self._skinJointNaming), str(point))]

        # create controllers
        pointControllers = []
        for joint in pointJoints:
            controller = self._create_controller(str(joint).replace('joint', 'ctr'), 'pole', 2, 10)
            pm.xform(controller, ws=True, m=pm.xform(joint, ws=True, q=True, m=True))
            # hierarchy
            parent.addChild(controller)
            pointControllers.append(controller)

        # roots
        ARC.createRoots(pointControllers)

        # conenct to joints
        for i, joint in enumerate(pointJoints):
            pm.pointConstraint(pointControllers[i], joint, maintainOffset=False)
            pm.orientConstraint(pointControllers[i], joint, maintainOffset=False)
            ARC.DGUtils.connectAttributes(pointControllers[i], joint, ['scale'], 'XYZ')


    def _create_controller(self, name, controllerType, s=1.0, colorIndex=4):
        """
        Args:
            name: name of controller
            controllerType(str): from json controller types
        return:
            controller: pymel transformNode
            transformMatrix: stored position
        """
        controller = ARC.createController(name, controllerType, self._chName, self._path, s, colorIndex)
        return controller