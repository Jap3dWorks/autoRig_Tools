import pymel.core as pm
import re
from maya import OpenMaya
import ctrSaveLoadToJson
import ARCore
reload(ARCore)
reload(ctrSaveLoadToJson)  # review: reload

import inspect

import logging
logging.basicConfig()
logger = logging.getLogger('autoRig:')
logger.setLevel(logging.DEBUG)

# TODO: main Joints, naming pe. akona_foreArm_main. similar a joint name
# TODO: Name convention revision
# name convention:
# name_zone_side_function_extra_type:
# akona_spine_chest_IK_ctr
# akona_arm_left_foreArm_twist1_jnt

class RigAuto(object):

    def __init__(self, chName, path):
        """
        autoRig class tools
        """
        # TODO: create node Module or chName_rig_grp transform node with messages attributes to store connections
        self.chName = chName
        self.path = path
        self.joints = {}  # store joints
        self.ikControllers = {}
        self.fkControllers = {}
        self.ikHandles = {}

        # create necessary groups
        # check if noXform exist
        try:
            self.noXformGrp = pm.PyNode('%s_noXform_grp' % self.chName)
        except:
            self.noXformGrp = pm.group(name='%s_noXform_grp' % self.chName, empty=True)
            self.noXformGrp.inheritsTransform.set(False)
            pm.PyNode('%s_rig_grp' % self.chName).addChild(self.noXformGrp)

        # check if ctr_grp exist
        try:
            self.ctrGrp = pm.PyNode('%s_ctr_grp' % self.chName)
        except:
            self.ctrGrp = pm.group(name='%s_ctr_grp' % self.chName, empty=True)
            pm.PyNode('%s_rig_grp' % self.chName).addChild(self.ctrGrp)

        # create Main ctr
        try:
            self.mainCtr = pm.PyNode('%s_main_ctr' % self.chName)
            self.ctrGrp.addChild(self.mainCtr)
        except:
            self.mainCtr = self.create_controller('%s_main_ctr' % self.chName, 'main', 1, 18)
            self.ctrGrp.addChild(self.mainCtr)
        # connect main scale to grp joints
        ARCore.connectAttributes(self.mainCtr, pm.PyNode('%s_joints_grp' % self.chName), ['scale'], ['X', 'Y', 'Z'])

        # I think i don't need this
        self.methodNames = [x[0] for x in inspect.getmembers(self, predicate=inspect.ismethod) if 'auto' in x[0]]
        print (self.methodNames)


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
                    pm.addAttr(moduleNode, ln=connection, sn=connection,  attributeType='message')

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


    # TODO: zone var in names
    #@checker_auto('decorated')
    def spine_auto(self, zone='spine', *funcs):
        """
            Auto create a character spine
        """
        # detect spine joints and their positions
        spineJoints = [point for point in pm.ls() if re.match('^%s.*%s.*skin_joint$' % (self.chName, zone), str(point))]
        positions = [point.getTranslation(space='world') for point in spineJoints]
        logger.debug('Spine joints: %s' % spineJoints)

        spineCurveTransform = pm.curve(ep=positions, name='%s_%s_1_crv' % (self.chName, zone))
        # parent to nXform grp
        noXformSpineGrp = pm.group(empty=True, name='%s_noXform_%s_grp' % (self.chName, zone))
        noXformSpineGrp.inheritsTransform.set(False)
        self.noXformGrp.addChild(noXformSpineGrp)
        noXformSpineGrp.addChild(spineCurveTransform)

        # curve shape node
        spineCurve = spineCurveTransform.getShape()

        #rebuildCurve
        pm.rebuildCurve(spineCurve, s=2, rpo=True, ch=False, rt=0, d=3, kt=0, kr=0)

        # review: test autoMethod
        ARCore.snapCurveToPoints(spineJoints, spineCurve, 16, 0.01)

        #TODO: nameController variable
        # create locators and connect to curve CV's
        spineDrvList = []
        self.spineIKControllerList = []
        spineFKControllerList = []
        for n, point in enumerate(spineCurve.getCVs()):
            ctrType = 'hips' if n == 0 else 'chest' if n == spineCurve.numCVs() - 1 else 'spine%s' % n
            # create grp to manipulate the curve
            spineDriver = pm.group(name='%s_Curve_%s_%s_drv' % (self.chName, zone, ctrType), empty=True)
            spineDriver.setTranslation(point)
            decomposeMatrix = pm.createNode('decomposeMatrix', name='%s_%s_%s_decomposeMatrix' % (self.chName, zone, ctrType))
            spineDriver.worldMatrix[0].connect(decomposeMatrix.inputMatrix)
            decomposeMatrix.outputTranslate.connect(spineCurve.controlPoints[n])
            spineDrvList.append(spineDriver)

            # create controller and parent locator
            spineController = self.create_controller('%s_%s_%s_1_ik_ctr' % (self.chName, zone, ctrType), '%sIk' % ctrType, 1, 17)
            logger.debug('spine controller: %s' % spineController)

            spineController.setTranslation(point)

            spineController.addChild(spineDriver)
            self.spineIKControllerList.append(spineController)

            # create FK controllers
            if n < 3:
                # first fk controller bigger
                fkCtrSize = 1.5 if len(spineFKControllerList) == 0 else 1
                spineFKController = self.create_controller('%s_%s_%s_fk_ctr' % (self.chName, zone, n + 1), 'hipsFk', fkCtrSize, 4)
                spineFKController.setTranslation(point)
                spineFKControllerList.append(spineFKController)

                # Fk hierarchy
                if len(spineFKControllerList) > 1:
                    spineFKControllerList[n-1].addChild(spineFKController)
                    logger.debug('parent %s, child %s' % (spineFKControllerList[-1], spineFKController))

            # configure ctr hierarchy, valid for 5 ctrllers
            if n == 1:
                self.spineIKControllerList[0].addChild(spineController)
                spineFKControllerList[0].addChild(self.spineIKControllerList[0])
            # last iteration
            elif n == (spineCurve.numCVs()-1):
                spineController.addChild(self.spineIKControllerList[-2])
                spineFKControllerList[-1].addChild(spineController)

                # add 3th ik controller to hierarchy too
                spineFKControllerList[1].addChild(self.spineIKControllerList[2])
                self.mainCtr.addChild(spineFKControllerList[0])

        # create roots grp
        ARCore.createRoots(spineFKControllerList)
        spineControllerRootsList = ARCore.createRoots(self.spineIKControllerList)

        # create points on curve that will drive the joints
        # this is like the main joint.
        self.jointDriverList = []
        ObjectUpVectorList = []
        for n, joint in enumerate(spineJoints):
            # jointPosition
            jointPos = joint.getTranslation('world')

            # nurbsCurve MFn
            selectionList = OpenMaya.MSelectionList()
            selectionList.add(str(spineCurve))
            dagPath = OpenMaya.MDagPath()
            selectionList.getDagPath(0, dagPath)
            mfnNurbCurve = OpenMaya.MFnNurbsCurve(dagPath)

            # get curveParam
            util = OpenMaya.MScriptUtil()
            util.createFromDouble(0.0)
            ptr = util.asDoublePtr()
            mfnNurbCurve.getParamAtPoint(OpenMaya.MPoint(jointPos[0], jointPos[1], jointPos[2]), ptr, 1.0)
            param = util.getDouble(ptr)

            # create empty grp and connect nodes
            jointNameSplit = str(joint).split('_')[1]
            jointDriverGrp = pm.group(empty=True, name='%s_drv_%s_%s_%s_drv' % (self.chName, zone, jointNameSplit, n+1))
            # jointDriverGrp = pm.spaceLocator(name='%s_target' % str(joint))
            pointOnCurveInfo = pm.createNode('pointOnCurveInfo', name='%s_drv_%s_%s_%s_positionOnCurveInfo' % (self.chName, zone, jointNameSplit, n+1))
            spineCurve.worldSpace[0].connect(pointOnCurveInfo.inputCurve)
            pointOnCurveInfo.parameter.set(param)
            pointOnCurveInfo.position.connect(jointDriverGrp.translate)
            noXformSpineGrp.addChild(jointDriverGrp)
            # drive joint by a parent constraint
            self.jointDriverList.append(jointDriverGrp)

            # index to assign upVector Object
            objUpVectorIndex = -1
            # up vector transforms, useful for later aimContraint
            if not n ==len(spineJoints)-1:
                ObjectUpVector = pm.group(empty=True, name='%s_drv_%s_%s_%s_upVector' % (self.chName,zone,jointNameSplit, n+1))
                # ObjectUpVector = pm.spaceLocator(name='%s_upVector' % str(joint))
                ObjectUpVector.setTranslation(jointDriverGrp.getTranslation() + pm.datatypes.Vector(0, 0, -20), 'world')
                noXformSpineGrp.addChild(ObjectUpVector)
                ObjectUpVectorList.append(ObjectUpVector)
                # if not last iteration index -1
                objUpVectorIndex = -2
            # AimConstraint locators, each locator aim to the upper locator
            if n == 0:
                # parent first ObjectUpVector, to hips controller
                self.spineIKControllerList[0].addChild(ObjectUpVector)
            else:
                aimConstraint = pm.aimConstraint(self.jointDriverList[-1], self.jointDriverList[-2], aimVector=(1,0,0), upVector=(0,1,0), worldUpType='object', worldUpObject=ObjectUpVectorList[objUpVectorIndex])


        # parent last target transform, to chest
        self.spineIKControllerList[-1].addChild(ObjectUpVectorList[-1])

        # objectUpVector conections, by pointContraint
        totalDistance = ObjectUpVectorList[-1].getTranslation('world') - ObjectUpVectorList[0].getTranslation('world')
        logger.debug('totalDistance: %s' % totalDistance)
        totalDistance = totalDistance.length()
        logger.debug('totalDistance: %s' % totalDistance)

        # can't do this before, because we need de first and the last upVectorObjects to config the pointConstraints
        # connect ipVectorObjects with point constraint
        for n, upVectorObject in enumerate(ObjectUpVectorList):
            if n == 0 or n == len(ObjectUpVectorList)-1:
                continue
            jointNameSplit = str(spineJoints[n]).split('_')[1]
            distance = upVectorObject.getTranslation('world') - ObjectUpVectorList[0].getTranslation('world')
            distance = distance.length()
            pointConstraintFactor = distance/totalDistance

            pointContraint = pm.pointConstraint(ObjectUpVectorList[-1], ObjectUpVectorList[0], upVectorObject, maintainOffset=False, name='%s_drv_%s_%s_upVector_pointConstraint' % (self.chName,zone,jointNameSplit))
            pointContraint.attr('%sW0' % str(ObjectUpVectorList[-1])).set(pointConstraintFactor)
            pointContraint.attr('%sW1' % str(ObjectUpVectorList[0])).set(1-pointConstraintFactor)

        for n, joint in enumerate(spineJoints):
            # for each joint, create a multiply divide node
            # formula for scale: 1+(factorScale - 1)*influence
            # TODO: rename all this

            jointNameSplit = str(joint).split('_')[1]  # review, maybe better store joints name in a list

            # TODO: do this more legible if it is possible
            if re.match('.*(end|hips).*', str(joint)):
                # last joint and first joint connect to controller
                # if hips, use de min val, zero. when end, n will be bigger than ik controllers, so use  the last ik controller.
                spineIkCtrConstr = self.spineIKControllerList[min(n, len(self.spineIKControllerList)-1)]
                spineIkCtrConstr.rename(str(joint).replace('joint', 'ctr').replace('skin','main'))  # rename ctr, useful for snap proxy model
                # constraint
                pm.pointConstraint(self.jointDriverList[n], joint, maintainOffset=False,  name='%s_drv_%s_%s_1_pointConstraint' % (self.chName, zone, jointNameSplit))
                endJointOrientConstraint = pm.orientConstraint(self.spineIKControllerList[min(n, len(self.spineIKControllerList)-1)], joint, maintainOffset=True, name='%s_drv_%s_%s_1_orientConstraint' % (self.chName, zone, jointNameSplit))
                endJointOrientConstraint.interpType.set(0)

            else:
                # connect to deform joints
                self.jointDriverList[n].rename(str(joint).replace('skin', 'main'))  # rename driver, useful for snap proxy model
                pm.parentConstraint(self.jointDriverList[n], joint, maintainOffset=True, name='%s_drv_%s_%s_1_parentConstraint' % (self.chName, zone, jointNameSplit))

        # stretch TODO: print spineJoints list
        ARCore.stretchCurveVolume(spineCurve, spineJoints, '%s_%s' % (self.chName, zone), self.mainCtr)

        # lock and hide attributes
        ARCore.lockAndHideAttr(self.spineIKControllerList[1:-1], False, True, True)  # ik Ctr, no hips and chest
        ARCore.lockAndHideAttr(spineFKControllerList[1:], True, False, True)  # fk controller list, no hips
        ARCore.lockAndHideAttr(spineFKControllerList[0], False, False, True)  # fk controller hips
        ARCore.lockAndHideAttr([self.spineIKControllerList[0], self.spineIKControllerList[-1]], False, False, True)  # ik Ctr, hips and chest

        # function for create extra content
        for func in funcs:
            ikControllers, fkControllers = func()
            #self.spineIKControllerList = self.spineIKControllerList + ikControllers
            #spineFKControllerList = spineFKControllerList + fkControllers

        # save data
        self.joints[zone] = spineJoints
        self.ikControllers[zone] = self.spineIKControllerList
        self.fkControllers[zone] = spineFKControllerList
        return self.spineIKControllerList, spineFKControllerList

    def neckHead_auto(self, zone='neckHead', *funcs):
        """
        Create neck head system
        :param zone:
        :param funcs:
        :return:
        """
        self.lastZone=zone
        # store joints, not end joint
        neckHeadJoints = [point for point in pm.ls() if re.match('^%s.%s.*skin_joint$' % (self.chName, zone), str(point))]
        logger.debug('Neck head joints: %s' % neckHeadJoints)
        positions = [point.getTranslation(space='world') for point in neckHeadJoints[:-1]]

        neckHeadCurveTransform = pm.curve(ep=positions, name='%s_%s1_crv' % (self.chName, zone))
        # parent to noXform grp
        noXformNeckHeadGrp = pm.group(empty=True, name='%s_%s_noXform_grp' % (self.chName, zone))
        noXformNeckHeadGrp.inheritsTransform.set(False)
        self.noXformGrp.addChild(noXformNeckHeadGrp)
        noXformNeckHeadGrp.addChild(neckHeadCurveTransform)

        neckHeadCurve = neckHeadCurveTransform.getShape()

        # rebuildCurve
        pm.rebuildCurve(neckHeadCurve, s=2, rpo=True, ch=False, rt=0, d=3, kt=0, kr=0)
        ARCore.snapCurveToPoints(neckHeadJoints[:-1], neckHeadCurve, 16, 0.01)

        # create locators and connect to curve CV's
        neckHeadDrvList = []
        self.neckHeadIKCtrList = []
        neckHeadFKCtrList = []

        for n, point in enumerate(neckHeadCurve.getCVs()):
            # create drivers to manipulate the curve
            neckHeadDriver = pm.group(name='%s_%s_%s_curve_drv' % (self.chName, zone, n+1), empty=True)
            neckHeadDriver.setTranslation(point)
            # use the worldMatrix
            decomposeMatrix = pm.createNode('decomposeMatrix', name='%s_%s_%s_decomposeMatrix' % (self.chName,zone, n+1))
            neckHeadDriver.worldMatrix[0].connect(decomposeMatrix.inputMatrix)
            decomposeMatrix.outputTranslate.connect(neckHeadCurve.controlPoints[n])
            # set last ik spine controller as parent
            self.ikControllers['spine'][-1].addChild(neckHeadDriver)
            neckHeadDrvList.append(neckHeadDriver)  # add to drv List

            # no create controller two first drivers and the penultimate
            # TODO: better continue after if
            if n > 1 and not n == neckHeadCurve.numCVs()-2:
                # create controller and parent drivers to controllers
                ctrType = 'neck' if not len(self.neckHeadIKCtrList) else 'head'
                neckHeadIKCtr = self.create_controller('%s_%s_%s_ik_ctr' % (self.chName, zone, ctrType), '%sIk' % ctrType, 1, 17)
                logger.debug('neckHead controller: %s' % neckHeadIKCtr)

                if n == neckHeadCurve.numCVs() - 1:  # las iteration
                    lastSpineIkController = self.neckHeadIKCtrList[-1].getTranslation('world')
                    neckHeadIKCtr.setTranslation((point[0], point[1], point[2]))
                else:
                    neckHeadIKCtr.setTranslation(neckHeadJoints[1].getTranslation('world'), 'world')  # controller and joint same position

                neckHeadIKCtr.addChild(neckHeadDriver)
                self.neckHeadIKCtrList.append(neckHeadIKCtr)  # add to ik controller List

                # create FK controllers, only with the first ik controller
                if len(self.neckHeadIKCtrList) == 1:
                    neckHeadFKCtr = self.create_controller('%s_%s_%s1_fk_ctr' % (self.chName, zone, ctrType), 'neckFk1',1,4)
                    neckHeadFKCtr.setTranslation(neckHeadJoints[0].getTranslation('world'), 'world')
                    neckHeadFKCtrList.append(neckHeadFKCtr)

                    neckHeadFKCtr2 = self.create_controller('%s_%s_%s2_fk_ctr' % (self.chName, zone, ctrType), 'neckFk', 1, 4)
                    neckHeadFKCtr2.setTranslation(neckHeadJoints[1].getTranslation('world'), 'world')
                    neckHeadFKCtrList.append(neckHeadFKCtr2)
                    # create hierarchy
                    neckHeadFKCtr.addChild(neckHeadFKCtr2)
                    neckHeadFKCtr2.addChild(neckHeadIKCtr)

                    # Fk hierarchy, if we have more fk controllers. not the case TODO: more procedural
                    if len(neckHeadFKCtrList) > 2:
                        neckHeadFKCtrList[n-1].addChild(neckHeadFKCtr)
                        logger.debug('parent %s, child %s' % (neckHeadFKCtrList[-1], neckHeadFKCtr))

        # configure ctr hierarchy
        neckHeadFKCtrList[-1].addChild(self.neckHeadIKCtrList[-1])
        self.neckHeadIKCtrList[-1].addChild(neckHeadDrvList[-2])  # add the penultimate driver too
        #self.ikControllers['spine'][-1].addChild(self.neckHeadIKCtrList[0])  # ik controller child of last spine controller
        self.neckHeadIKCtrList[0].addChild(neckHeadDrvList[1])
        # rename head control
        self.neckHeadIKCtrList[-1].rename('%s_%s_head_1_IK_ctr' % (self.chName, zone))  # review: better here or above?
        # Fk parent to last ik spine controller
        self.ikControllers['spine'][-1].addChild(neckHeadFKCtrList[0])

        # create roots grp
        neckHeadFKCtrRoots = ARCore.createRoots(neckHeadFKCtrList)
        neckHeadIKCtrRoots = ARCore.createRoots(self.neckHeadIKCtrList)

        # head orient auto, isolate
        # head orient neck grp
        neckOrientAuto = pm.group(empty=True, name='%s_orientAuto_%s_head_1_grp' % (self.chName, zone))
        neckOrientAuto.setTranslation(self.neckHeadIKCtrList[-1].getTranslation('world'), 'world')
        neckHeadFKCtrList[-1].addChild(neckOrientAuto)

        headIkAutoGrp = pm.group(empty=True, name='%s_orientAuto_%s_head_ikAuto_1_grp' % (self.chName, zone))
        headIkAutoGrp.setTranslation(self.neckHeadIKCtrList[-1].getTranslation('world'), 'world')
        neckHeadFKCtrList[-1].addChild(headIkAutoGrp)
        headIkAutoGrp.addChild(neckHeadIKCtrRoots[-1])

        # head orient base grp
        baseOrientAuto = pm.group(empty=True, name='%s_orientAuto_%s_head_base_1_grp' % (self.chName, zone))
        baseOrientAuto.setTranslation(neckOrientAuto.getTranslation('world'), 'world')
        self.mainCtr.addChild(baseOrientAuto)

        # create driver attr
        pm.addAttr(self.neckHeadIKCtrList[-1], longName='isolateOrient', shortName='isolateOrient', minValue=0.0,
                   maxValue=1.0, type='float', defaultValue=0.0, k=True)
        pm.addAttr(self.neckHeadIKCtrList[-1], longName='isolatePoint', shortName='isolatePoint', minValue=0.0,
                   maxValue=1.0, type='float', defaultValue=0.0, k=True)

        # constraint head controller offset to orient auto grps
        autoOrientConstraint = pm.orientConstraint(baseOrientAuto, neckOrientAuto, headIkAutoGrp, maintainOffset=False, name='%s_autoOrient_%s_head_1_orientConstraint' % (self.chName, zone))
        autoPointConstraint = pm.pointConstraint(baseOrientAuto, neckOrientAuto, headIkAutoGrp, maintainOffset=False, name='%s_autoOrient_%s_head_1_pointConstraint' % (self.chName, zone))

        # create Nodes and connect
        self.neckHeadIKCtrList[-1].isolateOrient.connect(autoOrientConstraint.attr('%sW0' % str(baseOrientAuto)))
        self.neckHeadIKCtrList[-1].isolatePoint.connect(autoPointConstraint.attr('%sW0' % str(baseOrientAuto)))

        plusMinusAverageOrient = pm.createNode('plusMinusAverage', name='%s_orientAuto_%s_head_isolateOrient_1_plusMinusAverage' % (self.chName, zone))
        plusMinusAveragepoint = pm.createNode('plusMinusAverage', name='%s_pointAuto_%s_head_isolateOrient_1_plusMinusAverage' % (self.chName, zone))
        self.neckHeadIKCtrList[-1].isolateOrient.connect(plusMinusAverageOrient.input1D[1])
        self.neckHeadIKCtrList[-1].isolatePoint.connect(plusMinusAveragepoint.input1D[1])

        plusMinusAverageOrient.input1D[0].set(1)
        plusMinusAveragepoint.input1D[0].set(1)
        plusMinusAverageOrient.operation.set(2)
        plusMinusAveragepoint.operation.set(2)
        plusMinusAverageOrient.output1D.connect(autoOrientConstraint.attr('%sW1' % str(neckOrientAuto)))
        plusMinusAveragepoint.output1D.connect(autoPointConstraint.attr('%sW1' % str(neckOrientAuto)))

        # create points on curve that will drive the joints
        # this is like main joint
        self.neckHeadJointDriverList = []
        ObjectUpVectorList = []
        for n, joint in enumerate(neckHeadJoints[:-1]):
            # jointPosition
            jointPos = joint.getTranslation('world')

            # nurbsCurve MFn
            selectionList = OpenMaya.MSelectionList()
            selectionList.add(str(neckHeadCurve))
            dagPath = OpenMaya.MDagPath()
            selectionList.getDagPath(0, dagPath)
            mfnNurbCurve = OpenMaya.MFnNurbsCurve(dagPath)

            # get curveParam
            util = OpenMaya.MScriptUtil()
            util.createFromDouble(0.0)
            ptr = util.asDoublePtr()
            try:
                mfnNurbCurve.getParamAtPoint(OpenMaya.MPoint(jointPos[0], jointPos[1], jointPos[2]), ptr, 1.0)
                param = util.getDouble(ptr)
            except:
                param = 1.0
            # create empty grp and connect nodes
            jointNameSplit = str(joint).split('_')[1]
            jointDriverGrp = pm.group(empty=True, name='%s_drv_%s_%s_%s_drv' % (self.chName, zone, jointNameSplit, n+1))
            # jointDriverGrp = pm.spaceLocator(name='%s_target' % str(joint))
            pointOnCurveInfo = pm.createNode('pointOnCurveInfo', name='%s_drv_%s_%s_%s_positionOnCurveInfo' % (self.chName, zone, jointNameSplit, n+1))
            neckHeadCurve.worldSpace[0].connect(pointOnCurveInfo.inputCurve)
            pointOnCurveInfo.parameter.set(param)
            pointOnCurveInfo.position.connect(jointDriverGrp.translate)
            noXformNeckHeadGrp.addChild(jointDriverGrp)
            # drive joint by a parent constraint
            self.neckHeadJointDriverList.append(jointDriverGrp)

            # up vector transforms, useful for later aimContraint
            ObjectUpVector = pm.group(empty=True, name='%s_upVector' % str(joint))
            # ObjectUpVector = pm.spaceLocator(name='%s_drv_%s_%s_%s_upVector' % (self.chName,zone,jointNameSplit, n+1))
            ObjectUpVector.setTranslation(jointDriverGrp.getTranslation() + pm.datatypes.Vector(0, 0, -20), 'world')
            noXformNeckHeadGrp.addChild(ObjectUpVector)
            ObjectUpVectorList.append(ObjectUpVector)

            # AimConstraint locators, each locator aim to the upper locator
            if n == 0:
                # parent first target transform, to hips controller
                self.ikControllers['spine'][-1].addChild(ObjectUpVector)
            if n > 0:
                aimConstraint = pm.aimConstraint(self.neckHeadJointDriverList[-1], self.neckHeadJointDriverList[-2], aimVector=(1, 0, 0),
                                                 upVector=(0, 1, 0), worldUpType='object', worldUpObject=ObjectUpVectorList[-2])

        # parent last target transform, to chest
        self.neckHeadIKCtrList[-1].addChild(ObjectUpVectorList[-1])

        # connect by pointConstraint objectUpVector from first to last upVectors
        totalDistance = ObjectUpVectorList[-1].getTranslation('world') - ObjectUpVectorList[0].getTranslation('world')
        totalDistance = totalDistance.length()
        for n, upVectorObject in enumerate(ObjectUpVectorList):
            if n == 0 or n == len(ObjectUpVectorList) - 1:
                continue
            distance = upVectorObject.getTranslation('world') - ObjectUpVectorList[0].getTranslation('world')
            distance = distance.length()
            pointConstraintFactor = distance / totalDistance

            pointContraint = pm.pointConstraint(ObjectUpVectorList[-1], ObjectUpVectorList[0], upVectorObject,
                                                maintainOffset=False, name='%s_drv_%s_%s_upVector_pointConstraint' % (self.chName, zone, jointNameSplit))
            pointContraint.attr('%sW0' % str(ObjectUpVectorList[-1])).set(pointConstraintFactor)
            pointContraint.attr('%sW1' % str(ObjectUpVectorList[0])).set(1 - pointConstraintFactor)

        for n, joint in enumerate(neckHeadJoints):
            # for each joint, create a multiply divide node
            # formula for scale: 1+(factorScale - 1)*influence
            # if is an end joint, do nothing
            # TODO: change Tip by end
            if 'Tip' in str(joint):
                continue

            jointNameSplit = str(joint).split('_')[1]
            # Constraint for the head zone
            # be careful with naming, this should be more procedural
            if '_head' in str(joint):
                # head joint, with point to driver, and orient to controller
                pm.pointConstraint(self.neckHeadJointDriverList[n], joint, maintainOffset=False, name='%s_%s_%s_1_drv_pointConstraint' % (self.chName, zone, jointNameSplit))
                # orient to controller
                self.neckHeadIKCtrList[-1].rename(str(joint).replace('skin', 'ctr'))  # rename, useful for snap proxy model
                pm.orientConstraint(self.neckHeadIKCtrList[-1], joint, maintainOffset=True, name='%s_%s_%s_1_drv_orientConstraint' % (self.chName, zone, jointNameSplit))
                # connect scales
                ARCore.connectAttributes(self.neckHeadIKCtrList[-1], joint, ['scale'], 'XYZ')

            else:
                self.neckHeadJointDriverList[n].rename(str(joint).replace('skin', 'main'))  # rename, useful for snap proxy model
                pm.parentConstraint(self.neckHeadJointDriverList[n], joint, maintainOffset=True, name='%s_%s_%s_1_drv_parentConstraint' % (self.chName, zone, jointNameSplit))

        # stretch
        ARCore.stretchCurveVolume(neckHeadCurve, neckHeadJoints[:-1], '%s_%s' % (self.chName, zone), self.mainCtr)

        # freeze and hide attributes.
        ARCore.lockAndHideAttr(neckHeadFKCtrList, False, False, True)
        # lock and hide neck attr, it's here because we have only one
        ARCore.lockAndHideAttr(self.neckHeadIKCtrList[0], False, True, True)

        # extra functions
        for func in funcs:
            ikControllers, fkControllers = func()
            self.neckHeadIKCtrList = self.neckHeadIKCtrList + ikControllers
            neckHeadFKCtrList = neckHeadFKCtrList + fkControllers

        # save data
        self.joints[zone] = neckHeadJoints
        self.ikControllers[zone] = self.neckHeadIKCtrList
        self.fkControllers[zone] = neckHeadFKCtrList
        return self.neckHeadIKCtrList, neckHeadFKCtrList

    #TODO: rename method ikFkChain_auto
    def ikFkChain_auto(self, side, parent, zone='leg', stretch=True, bendingBones=False, *funcs):
        """
        # TODO: organize and optimize this method
        auto build a ik fk Chain
        Args:
            side: left or right
            zone: name of the system zone
            stretch(bool): if true, create stretch system or hand
            restPoints(list):  with rest points
            bendingBones(bool): add a control per twist joint
        """
        zoneA = zone
        self.lastZone = zone  # review
        self.lastSide = side  # review
        fkColor = 14 if side == 'left' else 29
        # be careful with poseInterpolator
        ikFkJoints = [point for point in pm.ls() if re.match('^%s.*%s.*%s_.*?_(skin_joint)$' % (self.chName, zoneA, side), str(point).lower()) and not 'twist' in str(point)]
        self.ikFkTwistJoints = [point for point in pm.ls() if re.match('^%s.*%s.*%s.*(twist).*(skin_joint)$' % (self.chName, zoneA, side), str(point).lower())]
        logger.debug('%s %s joints: %s' % (side, zoneA, ikFkJoints))
        logger.debug('%s %s twist joints: %s' % (side, zoneA, self.ikFkTwistJoints))

        # group for ikFk controls
        self.ikFkCtrGrp = pm.group(empty=True, name='%s_ik_%s_%s_ctrGrp_root' % (self.chName, zoneA, side))
        self.mainCtr.addChild(self.ikFkCtrGrp)

        # sync ikFkTwistJoints index with ikFk joints index
        ikFkTwistSyncJoints = ARCore.syncListsByKeyword(ikFkJoints, self.ikFkTwistJoints, 'twist')

        # fk controllers are copies of ikFk joints
        # save controllers name
        self.ikFk_FkControllersList = []
        self.ikFk_IkControllerList = []
        self.ikFk_MainJointList = []
        ikFkTwistList = []
        self.ikFk_IkJointList = []

        NameIdList = []  # store idNames. p.e upperLeg, lowerLeg

        # duplicate joints
        # todo: no i variable
        for n, joint in enumerate(ikFkJoints):
            controllerName = str(joint).split('_')[3] if 'end' not in str(joint) else 'end'  # if is an end joint, rename end
            # fk controllers, last joint is an end joint, it doesn't has controller on the json controller file,
            # so tryCatch should give an error
            try:
                fkControl = self.create_controller('%s_%s_%s_%s_fk_ctr' % (self.chName, zoneA, side, controllerName), '%sFk_%s' % (controllerName, side), 1, fkColor)
                pm.xform(fkControl, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))
                self.ikFk_FkControllersList.append(fkControl)
            except:
                logger.debug('no controller for fk controller: %s' % joint)
                pass
            # ik and main joints
            self.ikFk_IkJointList.append(joint.duplicate(po=True, name='%s_%s_%s_%s_ik_joint' % (self.chName, zoneA, side, controllerName))[0])
            self.ikFk_MainJointList.append(joint.duplicate(po=True, name='%s_%s_%s_%s_main_joint' % (self.chName, zoneA, side, controllerName))[0])

            ### twist Joints ####
            if ikFkTwistSyncJoints[n]:
                ikFkTwistIni = [joint.duplicate(po=True, name='%s_twist0_%s_%s_%s_joint' % (self.chName, zoneA, side, controllerName))[0]]

                for j, twstJnt in enumerate(ikFkTwistSyncJoints[n]):
                    # duplicate and construc hierarchy
                    ikFkTwistIni.append(twstJnt.duplicate(po=True, name='%s_twist%s_%s_%s_%s_joint' % (self.chName, j+1, zoneA, side, controllerName))[0])
                    ikFkTwistIni[-2].addChild(ikFkTwistIni[-1])

                ikFkTwistList.append(ikFkTwistIni)  # append to list of tJoints
                self.mainCtr.addChild(ikFkTwistIni[0])

                # parent twist joints
                if n == 0:
                    parent.addChild(ikFkTwistIni[0])  # first to ctr ik hips
                else:
                    self.ikFk_MainJointList[-2].addChild(ikFkTwistIni[0])  # lower twist child of upper ikFk

                # create twist group orient tracker, if is chain before foot or hand, track foot or hand
                if ikFkTwistSyncJoints[n] == ikFkTwistSyncJoints[-2]:  # just before end joint
                    # This twist joints will be drive by another system, foot or hand in general, so we store the
                    # necessary info in some class attributes.
                    self.footTwstList = list(ikFkTwistIni)
                    self.footTwstZone = zoneA
                    self.footTwstCtrName = controllerName
                    self.footpointCnstr = self.ikFk_MainJointList[-1]

                else:
                    # connect and setup ikFk Twist Ini chain
                    ARCore.twistJointsConnect(ikFkTwistIni, self.ikFk_MainJointList[-1], '%s_%s_%s_%s' % (self.chName, controllerName, zoneA, side))

            NameIdList.append(controllerName)

        logger.debug('ikFk IK joints: %s' % self.ikFk_IkJointList)

        # reconstruct hierarchy
        # create Fk control shapes
        for i, fkCtr in enumerate(self.ikFk_FkControllersList):  # last joint does not has shape
            # ik hierarchy
            self.ikFk_IkJointList[i].addChild(self.ikFk_IkJointList[i + 1])
            # main hierarchy
            self.ikFk_MainJointList[i].addChild(self.ikFk_MainJointList[i + 1])
            # last it avoid this
            # fk controls
            if i != len(self.ikFk_FkControllersList)-1:
                fkCtr.addChild(self.ikFk_FkControllersList[i + 1])

        # ik control
        self.ikFk_IkControl = self.create_controller('%s_%s_%s_ik_ctr' % (self.chName, zoneA, side), '%sIk_%s' % (zoneA, side), 1, 17)
        self.ikFk_IkControl.setTranslation(ikFkJoints[-1].getTranslation('world'), 'world')
        self.ikFkCtrGrp.addChild(self.ikFk_IkControl)  # parent to ctr group

        # set hierarchy
        print self.ikFk_FkControllersList
        parent.addChild(self.ikFk_FkControllersList[0])
        parent.addChild(self.ikFk_MainJointList[0])
        parent.addChild(self.ikFk_IkJointList[0])

        # save to list
        self.ikFk_IkControllerList.append(self.ikFk_IkControl)
        ARCore.createRoots(self.ikFk_IkControllerList)

        # fkRoots
        self.ikFk_FkCtrRoots = ARCore.createRoots(self.ikFk_FkControllersList)
        ARCore.createRoots(self.ikFk_FkControllersList, 'auto')

        # set preferred angle
        self.ikFk_IkJointList[1].preferredAngleZ.set(-15)
        # ik solver
        ikHandle, ikEffector = pm.ikHandle(startJoint=self.ikFk_IkJointList[0], endEffector=self.ikFk_IkJointList[-1], solver='ikRPsolver', name='%s_ik_%s_%s_handle' % (self.chName, zoneA, side))
        ikEffector.rename('%s_ik_%s_%s_effector' % (self.chName, zoneA, side))
        self.ikFk_IkControl.addChild(ikHandle)
        # create poles
        ikFkPoleController = self.create_controller('%s_%s_%s_pole_ik_ctr' % (self.chName, zoneA, side), 'pole',2)
        ARCore.relocatePole(ikFkPoleController, self.ikFk_IkJointList, 35)  # relocate pole Vector
        self.ikFkCtrGrp.addChild(ikFkPoleController)
        pm.addAttr(ikFkPoleController, ln='polePosition', at='enum', en="world:root:foot", k=True)
        # save poleVector
        self.ikFk_IkControllerList.append(ikFkPoleController)

        # constraint poleVector
        pm.poleVectorConstraint(ikFkPoleController, ikHandle)

        # root poleVector
        ikFkPoleVectorAuto = ARCore.createRoots([ikFkPoleController])
        ARCore.createRoots([ikFkPoleController])

        # TODO: more abstract
        # poleVectorAttributes
        poleAttrgrp=[]
        ikFkPoleAnimNodes=[]
        for attr in ('world', 'root', zoneA):
            ikFkPoleGrp = pm.group(empty=True, name= '%s_ik_%s_%s_pole%s_grp' % (self.chName, zoneA, attr.capitalize(), side))
            poleAttrgrp.append(ikFkPoleGrp)
            pm.xform(ikFkPoleGrp, ws=True, m=pm.xform(ikFkPoleVectorAuto, ws=True, m=True, q=True))
            ikFkPoleAnim = pm.createNode('animCurveTU', name='%s_ik_%s_%s_pole%s_animNode' % (self.chName, zoneA, attr.capitalize(), side))
            ikFkPoleController.attr('polePosition').connect(ikFkPoleAnim.input)
            ikFkPoleAnimNodes.append(ikFkPoleAnim)

            if attr == 'world':
                ikFkPoleAnim.addKeyframe(0, 1)
                ikFkPoleAnim.addKeyframe(1, 0)
                ikFkPoleAnim.addKeyframe(2, 0)
                self.ikFkCtrGrp.addChild(ikFkPoleGrp)
            elif attr == 'root':
                ikFkPoleAnim.addKeyframe(0, 0)
                ikFkPoleAnim.addKeyframe(1, 1)
                ikFkPoleAnim.addKeyframe(2, 0)
                parent.addChild(ikFkPoleGrp)
            elif attr == zoneA:
                ikFkPoleAnim.addKeyframe(0, 0)
                ikFkPoleAnim.addKeyframe(1, 0)
                ikFkPoleAnim.addKeyframe(2, 1)
                self.ikFk_IkControl.addChild(ikFkPoleGrp)

        # once node are created, connect them
        polegrpsParentCnstr=pm.parentConstraint(poleAttrgrp[0],poleAttrgrp[1],poleAttrgrp[2], ikFkPoleVectorAuto, maintainOffset=False, name='%s_pointConstraint' % ikFkPoleVectorAuto)
        for i, poleAttr in enumerate(poleAttrgrp):
            ikFkPoleAnimNodes[i].output.connect(polegrpsParentCnstr.attr('%sW%s' % (str(poleAttr), i)))

        # main blending
        # unknown node to store blend info
        # locator shape instanced version
        ikFkNode = pm.spaceLocator(name='%s_%s_%s_attr' % (self.chName, zoneA, side))
        self.ikFkshape = ikFkNode.getShape()
        self.ikFkshape.visibility.set(0)
        pm.addAttr(self.ikFkshape, longName='ikFk', shortName='ikFk', minValue=0.0, maxValue=1.0, type='float', defaultValue=1.0, k=True)
        # hide unused attributes
        for attr in ('localPosition', 'localScale'):
            for axis in ('X', 'Y', 'Z'):
                pm.setAttr('%s.%s%s' % (self.ikFkshape, attr, axis), channelBox=False, keyable=False)

        self.plusMinusIkFk = pm.createNode('plusMinusAverage', name='%s_ikFk_blending_%s_%s_plusMinusAverage' % (self.chName, zoneA, side))
        self.ikFkshape.ikFk.connect(self.plusMinusIkFk.input1D[1])
        self.plusMinusIkFk.input1D[0].set(1)
        self.plusMinusIkFk.operation.set(2)

        if stretch:
            ###Strech###
            # fk strech
            # review this part, it could be cool only one func
            ikFk_MainDistances, ikFk_MaxiumDistance = ARCore.calcDistances(self.ikFk_MainJointList)  # review:  legIkJointList[0]   legIkCtrRoot
            #ikFkStretchSetup
            ARCore.stretchIkFkSetup(self.ikFk_FkCtrRoots[1:], ikFk_MainDistances, self.ikFkshape, [self.ikFk_IkJointList[0], ikHandle],
                                    ikFk_MaxiumDistance, self.ikFk_IkJointList[1:], self.ikFk_MainJointList[1:], ikFkTwistList, '%s_%s_%s' % (self.chName, zoneA, side), self.mainCtr, ikFkPoleController)

        # iterate along main joints
        # blending
        # todo: visibility, connect to ikFkShape
        # last joint of mainJointList is a end joint, do not connect
        for i, joint in enumerate(self.ikFk_MainJointList[:-1]):
            # attributes
            orientConstraint = pm.orientConstraint(self.ikFk_IkJointList[i], self.ikFk_FkControllersList[i], joint, maintainOffset=False, name='%s_%s_%s_main_blending_orientConstraint' % (self.chName, zoneA, side))
            self.ikFkshape.ikFk.connect(orientConstraint.attr('%sW0' % str(self.ikFk_IkJointList[i])))
            self.ikFkshape.ikFk.connect(self.ikFk_IkJointList[i].visibility)

            # parent shape
            self.ikFk_FkControllersList[i].addChild(self.ikFkshape, s=True, add=True)

            # conenct blendging node
            self.plusMinusIkFk.output1D.connect(orientConstraint.attr('%sW1' % str(self.ikFk_FkControllersList[i])))
            # review: visibility shape
            self.plusMinusIkFk.output1D.connect(self.ikFk_FkControllersList[i].visibility)

        # twist joints bending bones connect, if curve wire detected, no use bendingJoints
        # TODO: control by twist or wire?
        if ikFkTwistList:
            # if twist joints, we could desire bending controls or not
            if bendingBones:
                # todo: name args
                ARCore.twistJointBendingBoneConnect(parent, self.ikFk_MainJointList, ikFkTwistList, ikFkJoints, ikFkTwistSyncJoints, self.chName, zone, side, NameIdList, self.path)
            else:
                ARCore.twistJointConnect(self.ikFk_MainJointList, ikFkTwistList, ikFkJoints, ikFkTwistSyncJoints)

        # or connect the rig with not twist joints
        else:
            for i, joint in enumerate(self.ikFk_MainJointList):
                # connect to deform skeleton TODO: connect func, with rename options
                joint.rename(str(ikFkJoints[i]).replace('skin', 'main'))  # rename, useful for snap proxy model
                pm.orientConstraint(joint, ikFkJoints[i], maintainOffset=False, name='%s_main_%s_%s_parentConstraint' % (self.chName, zoneA, side))
                pm.pointConstraint(joint, ikFkJoints[i], maintainOffset=False, name='%s_main_%s_%s_parentConstraint' % (self.chName, zoneA, side))

        # ik blending controller attr
        self.ikFkshape.ikFk.connect(ikFkPoleController.visibility)
        self.ikFkshape.ikFk.connect(self.ikFk_IkControl.visibility)
        self.ikFk_IkControl.addChild(self.ikFkshape, add=True, s=True)

        # lock and hide attributes
        # lock and hide ik ctr scale attr
        ARCore.lockAndHideAttr(self.ikFk_IkControl, False, False, True)
        ARCore.lockAndHideAttr(self.ikFk_FkControllersList, True, False, True)
        ARCore.lockAndHideAttr(ikFkPoleController, False, True, True)

        # function for create foots or hands
        for func in funcs:
            ikControllers, fkControllers = func()
            self.ikFk_IkControllerList = self.ikFk_IkControllerList + ikControllers
            self.ikFk_FkControllersList = self.ikFk_FkControllersList + fkControllers

        # save Data
        zoneSide = '%s_%s' % (zoneA, side)
        self.joints[zoneSide] = ikFkJoints
        self.ikControllers[zoneSide] = self.ikFk_IkControllerList
        self.fkControllers[zoneSide] = self.ikFk_FkControllersList
        self.ikHandles[zoneSide] = ikHandle

        # delete ikfkShape
        pm.delete(ikFkNode)

        return self.ikFk_IkControllerList, self.ikFk_FkControllersList


    def foot_auto(self, zones=('foot', 'toe'), planeAlign=None, *funcs):
        """
        # TODO: organize and optimize this Func
        # TODO: get zoneA from last ikFk executed func
        This method should be called as a *arg for ikFkChain_auto.
        auto build a ik fk foot
        Args:
            side: left or right
            zone: foot
        """
        zoneB = zones[0]
        zoneC = zones[1]
        fkColor = 14 if self.lastSide =='left' else 29
        toesJoints = [point for point in pm.ls() if re.match('^%s.*%s.*%s.*%s.(?!End)(?!0)(?!twist).*skin_joint$' % (self.chName, zoneB, self.lastSide, zoneC), str(point))]
        #toesZeroJoints = [point for point in pm.ls() if re.match('^%s.*(%s).(?!_end)(?=0)(?!twist).*%s.*joint$' % (self.chName, zoneC, self.lastSide), str(point))]
        footJoints = [point for point in pm.ls() if re.match('^%s.*%s.*%s.*skin_joint$' % (self.chName, zoneB, self.lastSide), str(point)) and not zoneC in str(point)]

        # arrange toes by joint chain p.e [[toea, toesa_Tip], [toeb, toeb_tip]]
        toesJointsArr = ARCore.arrangeListByHierarchy(toesJoints)

        # controllers and main lists
        footFkControllerList = []  # fk lists
        toesFkControllerList = []
        footIkControllerList = []  # ik lists
        toesIkControllerList = []
        footMainJointsList = []  # main lists
        toesMainJointsList = []

        footControllerNameList = []
        toeControllerNameList = []
        # create foot ctr
        for joint in footJoints:
            controllerName = str(joint).split('_')[3]
            logger.debug('foot controller name: %s' % controllerName)
            footFkCtr = self.create_controller('%s_%s_%s_%s_fk_ctr' % (self.chName, zoneB, self.lastSide, controllerName),
                                               '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
            pm.xform(footFkCtr, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))

            footMain = joint.duplicate(po=True, name='%s_%s_%s_%s_main_joint' % (self.chName, zoneB, self.lastSide, controllerName))[0]

            # get transformMatrix and orient new controller
            matrix = pm.xform(footFkCtr, ws=True, q=True, m=True)

            matrix = ARCore.orientToPlane(matrix, planeAlign)  # adjusting orient to plane zx
            pm.xform(footFkCtr, ws=True, m=matrix)  # new transform matrix with vector adjust

            # fk control Shape
            shape = self.create_controller('%sShape' % str(footFkCtr), '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
            footFkCtr.addChild(shape.getShape(), s=True, r=True)
            pm.delete(shape)

            if not footFkControllerList:
                # save this matrix, to apply latter if necessary
                firstfootFkMatrix = matrix

            else:  # if more than 1 joint, reconstruct hierarchy
                footFkControllerList[-1].addChild(footFkCtr)
                footMainJointsList[-1].addChild(footMain)

            #save controllers
            footControllerNameList.append(controllerName)
            footFkControllerList.append(footFkCtr)
            footMainJointsList.append(footMain)

        # parent fk controller under leg.
        # can be the posibility that we have grps to control the stretch. so we look for childs
        fkControlChilds = self.ikFk_FkControllersList[-1].listRelatives(ad=True, type='transform')
        if fkControlChilds:
            fkControlChilds[0].addChild(footFkControllerList[0])
        else:
            self.ikFk_FkControllersList[-1].addChild(footFkControllerList[0])

        self.ikFk_MainJointList[-1].addChild(footMainJointsList[0])


        # twistJointsConnections
        if self.ikFkTwistJoints:
            ARCore.twistJointsConnect(self.footTwstList, footMainJointsList[0], '%s_%s_%s_%s' % (self.chName, self.footTwstCtrName, self.footTwstZone, self.lastSide), self.footpointCnstr)

        # TODO: function from joint, ik, fk, main?
        # create toe Fk and ik ctr
        toeIkCtrParents = []  # list with first joint of toes chains
        toeMainParents = []
        for i, toe in enumerate(toesJointsArr):
            toeFkChain = []
            toeIkChain = []
            toeMainChain = []
            for joint in toe:
                controllerName = str(joint).split('_')[3]
                logger.debug('foot controller name: %s' % controllerName)

                # create controllers and main
                toeFkCtr = self.create_controller('%s_%s_%s_%s_fk_ctr' % (self.chName, zoneB, self.lastSide, controllerName), '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
                pm.xform(toeFkCtr, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))

                toeMainJnt = joint.duplicate(po=True, name='%s_%s_%s_%s_main_joint' % (self.chName, zoneB, self.lastSide, controllerName))[0]

                toeIkCtr = self.create_controller('%s_%s_%s_%s_ik_ctr' % (self.chName, zoneB, self.lastSide, controllerName), '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
                pm.xform(toeIkCtr, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))

                # if joint Chain (not the first controller created), reconstruct hierarchy
                if toeFkChain:
                    toeFkChain[-1].addChild(toeFkCtr)
                    toeIkChain[-1].addChild(toeIkCtr)
                    toeMainChain[-1].addChild(toeMainJnt)

                toeFkChain.append(toeFkCtr)  # this list is reset every loop iteration
                toeIkChain.append(toeIkCtr)
                toeMainChain.append(toeMainJnt)

                toesFkControllerList.append(toeFkCtr)  # review: this variable?
                toesIkControllerList.append(toeIkCtr)
                toesMainJointsList.append(toeMainJnt)
                toeControllerNameList.append(controllerName)

            # middle toe, useful later to general toe controller
            if i == len(toesJointsArr) // 2:
                middleToeCtr = toeFkChain[0]
                middleToeCtrMatrix = pm.xform(middleToeCtr, q=True, ws=True, m=True)
                middleToeCtrIndex = i

            # construct foot hierarchy
            footFkControllerList[-1].addChild(toeFkChain[0])
            toeIkCtrParents.append(toeIkChain[0])  # ik ctr parent, for parent later in on ik ctrllers
            toeMainParents.append(toeMainChain[0])  # main parents
            logger.debug('toeIkchain: %s, %s' % (toeIkChain[0], type(toeIkChain[0])))
            logger.debug('toeIkCtrParents: %s' % (toeIkCtrParents))
            footMainJointsList[-1].addChild(toeMainChain[0])

        # ik foot ctr TODO: simplify this section
        footIkCtr = self.create_controller('%s_%s_%s_foot_ik_ctr' % (self.chName, zoneB, self.lastSide), '%sIk_%s' % (zoneB, self.lastSide), 1, 17)
        self.ikFkCtrGrp.addChild(footIkCtr)
        footIkControllerList.append(footIkCtr)  # append joint to list
        for toeCtr in toeIkCtrParents:
            footIkCtr.addChild(toeCtr)

        #--start rest points-- # todo: rest points modular, a function
        footIkAttrTypes = ['heel', 'tilt', 'toes', 'ball', 'footRoll']  # list with hierarchy order restPointsVariable, names complete
        # add auto attributes
        for attr in footIkAttrTypes:
            pm.addAttr(footIkCtr, longName=attr, shortName=attr, type='float', defaultValue=0.0, k=True)

        pm.addAttr(footIkCtr, longName='showControls', shortName='showControls', type='bool', defaultValue=True, k=False)
        pm.setAttr('%s.showControls' % str(footIkCtr), channelBox=True)

        footFootRollCtr=[]  # list of footRoll ctr

        for ctrType in footIkAttrTypes[:-1]:
            if ctrType == 'tilt':
                for inOut in ('In', 'Out'):
                    footIkCtrWalk = self.create_controller('%s_%s_%s_foot%s%s_ik_ctr' % (self.chName, zoneB, self.lastSide, ctrType.capitalize(), inOut),'foot%s%sIk_%s' % (ctrType.capitalize(),inOut, self.lastSide), 1, 17)
                    footIkControllerList[-1].addChild(footIkCtrWalk)
                    footIkCtr.attr('showControls').connect(footIkCtrWalk.getShape().visibility)
                    footIkControllerList.append(footIkCtrWalk)
            else:
                footIkCtrWalk = self.create_controller('%s_%s_%s_foot%s_ik_ctr' % (self.chName, zoneB, self.lastSide, ctrType.capitalize()), 'foot%sIk_%s' % (ctrType.capitalize(), self.lastSide), 1, 17)
                footIkControllerList[-1].addChild(footIkCtrWalk)
                footIkCtr.attr('showControls').connect(footIkCtrWalk.getShape().visibility)
                footFootRollCtr.append(footIkCtrWalk)  # save footRoll controllers

                if ctrType == 'toes':
                    footToesIkCtr = footIkCtrWalk
                elif ctrType == 'ball':
                    footBallIkCtr = footIkCtrWalk

                footIkControllerList.append(footIkCtrWalk)

        # once all foot controllers are created, translate if necessary
        pm.xform(footIkCtr, ws=True, m=firstfootFkMatrix)
        # relocateBall cotr, aligned with middle toe
        footBallIkMatrix = [firstfootFkMatrix[0],firstfootFkMatrix[1],firstfootFkMatrix[2],firstfootFkMatrix[3],
                                            firstfootFkMatrix[4],firstfootFkMatrix[5],firstfootFkMatrix[6],firstfootFkMatrix[7],
                                            firstfootFkMatrix[8],firstfootFkMatrix[9],firstfootFkMatrix[10],firstfootFkMatrix[11],
                                            middleToeCtrMatrix[12], middleToeCtrMatrix[13], middleToeCtrMatrix[14], middleToeCtrMatrix[15]]
        pm.xform(footBallIkCtr, ws=True, m=footBallIkMatrix)

        # parent toes Ik ctr to footToes
        logger.debug('toeIkCtrParents: %s' % toeIkCtrParents)
        for toeCtr in toeIkCtrParents:
            footToesIkCtr.addChild(toeCtr)

        # --end rest points--
        for i in self.ikFk_IkControl.listRelatives(c=True, type='transform'):  # traspase childs from previous leg controller
            footBallIkCtr.addChild(i)

        pm.delete(self.ikFk_IkControl.firstParent())  # if foot, we do not need this controller
        self.ikFk_IkControllerList.remove(self.ikFk_IkControl)

        # toes general Controller ik Fk review: no side review: ik ctrllers  simplyfy with for
        toeFkGeneralController = self.create_controller('%s_%s_%s_toeGeneral_fk_ctr' % (self.chName, zoneB, self.lastSide), 'toesFk', 1, fkColor)
        pm.xform(toeFkGeneralController, ws=True, m=middleToeCtrMatrix)  # align to middle individual toe review
        toeIkGeneralController = self.create_controller('%s_%s_%s_toeGeneral_ik_ctr' % (self.chName, zoneB, self.lastSide), 'toesFk', 1, fkColor)
        pm.xform(toeIkGeneralController, ws=True, m=middleToeCtrMatrix)
        # parent and store to lists
        footFkControllerList[-1].addChild(toeFkGeneralController)
        footToesIkCtr.addChild(toeIkGeneralController)
        toesFkControllerList.append(toeFkGeneralController)
        toesIkControllerList.append(toeIkGeneralController)

        # fk Roots and autos
        ARCore.createRoots(footFkControllerList)
        ARCore.createRoots(footFkControllerList, 'auto')
        ARCore.createRoots(footIkControllerList)
        footRollAuto = ARCore.createRoots(footFootRollCtr, 'footRollAuto')  # review: all in the same if
        footIkAuto = ARCore.createRoots(footIkControllerList, 'auto')
        ARCore.createRoots(toesFkControllerList)
        toesFkAuto = ARCore.createRoots(toesFkControllerList, 'auto')
        ARCore.createRoots(toesIkControllerList)
        toesIkAuto = ARCore.createRoots(toesIkControllerList, 'auto')

        # toe Statick  # review, move fingers
        if len(toeMainParents) > 1:
            for i, toeMainP in enumerate(toeMainParents):
                if i != middleToeCtrIndex:
                    pm.parentConstraint(toeMainParents[middleToeCtrIndex], toeMainP, skipRotate=('x','y','z'), maintainOffset=True)

        # connect toes rotate general attributes and set limits
        for ikOrFk in [toesFkAuto, toesIkAuto]:
            toesGeneralCtrIkOrFk = toeFkGeneralController if ikOrFk == toesFkAuto else toeIkGeneralController

            logger.debug('toesGeneralCtrIkOrFk: %s, %s' % (toesGeneralCtrIkOrFk, type(toesGeneralCtrIkOrFk)))
            for i, iAuto in enumerate(ikOrFk):
                if zoneC in str(iAuto) and '%sGeneral' % zoneC not in str(iAuto):
                    for axis in ('X', 'Y', 'Z'):
                        toesGeneralCtrIkOrFk.attr('rotate%s' % axis).connect(iAuto.attr('rotate%s' % axis))

        # footRollAuto __ rest points__
        # ik ctr autos
        for i, autoGrp in enumerate(footIkAuto[1:]):
            footIkControllerList[0].attr(footIkAttrTypes[i]).connect(autoGrp.rotateZ)
            if 'footTiltIn' in str(autoGrp):
                autoGrp.attr('minRotZLimitEnable').set(True)
                autoGrp.attr('minRotZLimit').set(0)
                footIkAttrTypes.insert(i, footIkAttrTypes[i])  # we have two tilt elements, so we add again the attr

            elif 'footTiltOut' in str(autoGrp):
                autoGrp.attr('maxRotZLimitEnable').set(True)
                autoGrp.attr('maxRotZLimit').set(0)

        for autoGrp in footRollAuto:
            logger.debug('footRoolAutoGrp: %s, %s' % (autoGrp, type(autoGrp)))
            animNode = pm.createNode('animCurveTU', name='%s_animNode' % autoGrp)
            footIkControllerList[0].attr(footIkAttrTypes[-1]).connect(animNode.input)
            animNode.output.connect(autoGrp.rotateZ)

            if 'heel' in str(autoGrp).lower():
                animNode.addKeyframe(-50, 50)
                animNode.addKeyframe(0, 0)
                animNode.addKeyframe(50, 0)
                keyFrames = range(animNode.numKeys())
                animNode.setTangentTypes(keyFrames, inTangentType='linear', outTangentType='linear')
                animNode.setTangentTypes([keyFrames[0],keyFrames[-1]], inTangentType='clamped', outTangentType='clamped')
                animNode.setPostInfinityType('linear')
                animNode.setPreInfinityType('linear')

            elif 'toes' in str(autoGrp).lower():
                animNode.addKeyframe(0, 0)
                animNode.addKeyframe(50, 0)
                animNode.addKeyframe(100, -90)
                keyFrames = range(animNode.numKeys())
                animNode.setTangentTypes(keyFrames, inTangentType='linear', outTangentType='linear')
                animNode.setTangentTypes([keyFrames[0], keyFrames[-1]], inTangentType='clamped',
                                         outTangentType='clamped')
                animNode.setPostInfinityType('linear')
                animNode.setPreInfinityType('linear')

            elif 'ball' in str(autoGrp).lower():
                animNode.addKeyframe(-50, 0)
                animNode.addKeyframe(0, 0)
                animNode.addKeyframe(50, -60)
                animNode.addKeyframe(100, 40)
                keyFrames = range(animNode.numKeys())
                animNode.setTangentTypes(keyFrames, inTangentType='linear', outTangentType='linear')
                animNode.setTangentTypes([keyFrames[0], keyFrames[-1]], inTangentType='clamped',
                                         outTangentType='clamped')
                animNode.setPostInfinityType('linear')
                animNode.setPreInfinityType('linear')
        # END footRollAuto __ rest points__

        ## BLEND ##
        # orient constraint main to ik or fk foot
        for i, mainJoint in enumerate(footMainJointsList):
            controllerName = footControllerNameList[i]
            if i == 0:
                # connect ik fk blend system, in a leg system only have one ik controller
                orientConstraint = pm.orientConstraint(footIkControllerList[-1], footFkControllerList[i], mainJoint, maintainOffset=True, name='%s_%s_%s_%s_mainBlending_orientConstraint' % (self.chName, controllerName, zoneB, self.lastSide))
                self.ikFkshape.ikFk.connect(orientConstraint.attr('%sW0' % str(footIkControllerList[-1])))  # shape with bleeding attribute
                self.ikFkshape.ikFk.connect(footIkControllerList[i].visibility)  # all foot chain visibility

                # parent ikFk shape
                footIkControllerList[0].addChild(self.ikFkshape, s=True, add=True)

                # parent ikFk shape
                footFkControllerList[0].addChild(self.ikFkshape, s=True, add=True)

                self.plusMinusIkFk.output1D.connect(orientConstraint.attr('%sW1' % str(footFkControllerList[i])))
                self.plusMinusIkFk.output1D.connect(footFkControllerList[i].getShape().visibility)

            else:
                pm.orientConstraint(footFkControllerList[i], mainJoint, maintainOffset=True, name='%s_%s_%s_%s_mainBlending_orientConstraint' % (self.chName, controllerName, zoneB, self.lastSide))

            # connect to deform skeleton
            mainJoint.rename(str(footJoints[i]).replace('skin', 'main'))  # rename, useful for snap proxy model
            pm.orientConstraint(mainJoint, footJoints[i], maintainOffset=False, name='%s_%s_%s_%s_joint_orientConstraint' % (self.chName, controllerName, zoneB, self.lastSide))

        ## TOES ##
        # main ik fk toes
        for i, mainJoint in enumerate(toesMainJointsList):
            controllerName = toeControllerNameList[i]
            # orient constraint only, if not, transitions from ik to fk are linear, and ugly
            orientConstraint = pm.orientConstraint(toesIkControllerList[i], toesFkControllerList[i], mainJoint, maintainOffset=True, name='%s_%s_%s_%s_mainBlending_orientConstraint' % (self.chName, controllerName, zoneB, self.lastSide))

            self.ikFkshape.ikFk.connect(orientConstraint.attr('%sW0' % str(toesIkControllerList[i])))  # shape with bleeding attribute
            self.ikFkshape.ikFk.connect(toesIkControllerList[i].visibility)  # all foot chain visibility

            self.plusMinusIkFk.output1D.connect(orientConstraint.attr('%sW1' % str(toesFkControllerList[i])))
            self.plusMinusIkFk.output1D.connect(toesFkControllerList[i].visibility)

            # connect to deform skeleton, review: point constraint toes main. strange behaviour
            mainJoint.rename(str(toesJoints[i]).replace('skin', 'main'))  # rename, useful for snap proxy model
            pm.orientConstraint(mainJoint, toesJoints[i], maintainOffset=False, name='%s_%s_%s_%s_joint_orientConstraint' % (self.chName, controllerName, self.lastZone, self.lastSide))
            pm.pointConstraint(mainJoint, toesJoints[i], maintainOffset=False, name='%s_%s_%s_%s_joint_pointConstraint' % (self.chName, controllerName, self.lastZone, self.lastSide))

        # total controllers
        footTotalFkControllers=footFkControllerList + toesFkControllerList

        # lock and hide attributes. after root creation
        ARCore.lockAndHideAttr(footTotalFkControllers, True, False, True)   # fk controllers
        #ARCore.lockAndHideAttr(toesIkControllerList[-1], True, False, True)
        ARCore.lockAndHideAttr(footIkControllerList[0], False, False, True)  # ik ctr foot
        ARCore.lockAndHideAttr(footIkControllerList[1:], True, False, True)  # walk ik controllers
        ARCore.lockAndHideAttr(toesIkControllerList, True, False, True)  # toes ik controllers


        return footIkControllerList + toesIkControllerList, footTotalFkControllers

    def hand_auto(self, zones=('hand', 'finger'), planeAlign=None, *funcs):
        """
        This method should be called as a *arg for ikFkChain_auto.
        auto build hand
        Args:
            side:
            zones:
            *funcs:
        Returns:
        """
        zoneB = zones[0]
        zoneC = zones[1]
        fkColor = 14 if self.lastSide == 'left' else 29  # review, more procedural
        # don't get zero joints, this do not has control
        fingerJoints = [point for point in pm.ls() if re.match('^%s.*%s.*%s.*%s.(?!End)(?!0)(?!twist).*skin_joint$' % (self.chName,zoneB, self.lastSide, zoneC), str(point))]
        # here get zero joints, this do not has control
        fingerZeroJoints = [point for point in pm.ls() if re.match('^%s.*%s.*%s.*%s.(?!End)(?=0)(?!twist).*skin_joint$' % (self.chName, zoneB, self.lastSide, zoneC), str(point))]
        # get hand joints
        handJoints = [point for point in pm.ls() if re.match('^%s.*%s.*%s.*((?!twist).).*skin_joint$' % (self.chName, zoneB, self.lastSide), str(point)) and not zoneC in str(point)]

        # arrange toes by joint chain p.e [[toea, toesa_Tip], [toeb, toeb_tip]]
        fingerJointsArr = ARCore.arrangeListByHierarchy(fingerJoints)
        logger.debug('Finger arranged list %s %s: %s' % (zoneB, self.lastSide, fingerJointsArr))

        # controllers and main lists
        handFkControllerList = []  # fk lists
        handIkControllerList = []  # ik lists
        handMainJointsList = []  # main lists
        fingerMainJointsList = []

        handControllerNameList = []
        fingerControllerNameList = []
        # create hand ctr
        for joint in handJoints:
            controllerName = str(joint).split('_')[3]
            logger.debug('foot controller name: %s' % controllerName)
            handFkCtr = self.create_controller('%s_%s_%s_%s_fk_ctr' % (self.chName, zoneB, self.lastSide, controllerName), '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
            pm.xform(handFkCtr, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))

            handMain = joint.duplicate(po=True, name='%s_%s_%s_%s_main_joint' % (self.chName, zoneB, self.lastSide, controllerName))[0]

            # get transformMatrix and orient new controller TODO: function
            matrix = pm.xform(handFkCtr, ws=True, q=True, m=True)

            matrix = ARCore.orientToPlane(matrix, planeAlign)  # adjusting orient to plane zx
            pm.xform(handFkCtr, ws=True, m=matrix)  # new transform matrix with vector adjust

            if not handFkControllerList:
                # save this matrix, to apply latter if necessary
                firstfootFkMatrix = matrix

            else:  # if more than 1 joint, reconstruct hierarchy
                handFkControllerList[-1].addChild(handFkCtr)
                handMainJointsList[-1].addChild(handMain)

            # save controllers
            handControllerNameList.append(controllerName)
            handFkControllerList.append(handFkCtr)
            handMainJointsList.append(handMain)

        # parent fk controller under ikFk chain
        fkControlChilds = self.ikFk_FkControllersList[-1].listRelatives(ad=True, type='transform')
        if fkControlChilds:
            fkControlChilds[0].addChild(handFkControllerList[0])
        else:
            self.ikFk_FkControllersList[-1].addChild(handFkControllerList[0])

        self.ikFk_MainJointList[-1].addChild(handMainJointsList[0])

        # twistJointsConnections
        if self.ikFkTwistJoints:
            ARCore.twistJointsConnect(self.footTwstList, handMainJointsList[0],
                                      '%s_%s_%s_%s' % (self.chName, self.footTwstCtrName, self.footTwstZone, self.lastSide),
                                      self.footpointCnstr)

        # create finger Fk and ik ctr
        # last hand fkCtr, easiest access later
        fingerMainParents = []
        for i, toe in enumerate(fingerJointsArr):
            fingerMainChain = []
            for joint in toe:
                controllerName = str(joint).split('_')[3]
                logger.debug('foot controller name: %s' % controllerName)
                # review
                fingerMainJnt = self.create_controller('%s_%s_%s_%s_fk_ctr' % (self.chName, zoneB, self.lastSide, controllerName), '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
                pm.xform(fingerMainJnt, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))

                # if joint Chain, reconstruct hierarchy
                if fingerMainChain:
                    fingerMainChain[-1].addChild(fingerMainJnt)

                fingerMainChain.append(fingerMainJnt)
                fingerMainJointsList.append(fingerMainJnt)
                fingerControllerNameList.append(controllerName)

            # construct hand hierarchy
            fingerMainParents.append(fingerMainChain[0])  # main parents
            handMainJointsList[-1].addChild(fingerMainChain[0])

        # ik hand ctr
        handIkCtr = self.create_controller('%s_%s_%s_hand_ik_ctr' % (self.chName, zoneB, self.lastSide), '%sIk_%s' % (zoneB, self.lastSide), 1, 17)
        self.ikFkCtrGrp.addChild(handIkCtr)
        handIkControllerList.append(handIkCtr)  # append joint to list

        for i in self.ikFk_IkControl.listRelatives(c=True, type='transform'):  # traspase childs from previous hand controller
            handIkCtr.addChild(i)

        pm.delete(self.ikFk_IkControl.firstParent())  # if foot, we do not need this controller
        self.ikFk_IkControllerList.remove(self.ikFk_IkControl)

        # fk Roots and autos
        ARCore.createRoots(handFkControllerList)
        ARCore.createRoots(handFkControllerList, 'auto')
        ARCore.createRoots(handIkControllerList)
        footIkAuto = ARCore.createRoots(handIkControllerList, 'auto')
        ARCore.createRoots(fingerMainJointsList)
        toesIkAuto = ARCore.createRoots(fingerMainJointsList, 'auto')

        ## BLEND ##
        # orient constraint main to ik or fk foot
        for i, mainJoint in enumerate(handMainJointsList):
            controllerName = handControllerNameList[i]
            if i == 0:
                # connect ik fk blend system, in a leg system only have one ik controller
                orientConstraint = pm.orientConstraint(handIkControllerList[-1], handFkControllerList[i], mainJoint, maintainOffset=True,
                                                       name='%s_%s_%s_%s_mainBlending_orientConstraint' % (self.chName, self.lastZone, controllerName, self.lastSide))
                self.ikFkshape.ikFk.connect(orientConstraint.attr('%sW0' % str(handIkControllerList[-1])))  # shape with bleeding attribute
                self.ikFkshape.ikFk.connect(handIkControllerList[i].visibility)  # all foot chain visibility

                # parent ikFk shape
                handIkControllerList[0].addChild(self.ikFkshape, s=True, add=True)

                # parent ikFk shape
                handFkControllerList[0].addChild(self.ikFkshape, s=True, add=True)

                self.plusMinusIkFk.output1D.connect(orientConstraint.attr('%sW1' % str(handFkControllerList[i])))
                self.plusMinusIkFk.output1D.connect(handFkControllerList[i].getShape().visibility)

            else:
                pm.orientConstraint(handFkControllerList[i], mainJoint, maintainOffset=True,
                                                       name='%s_%s_%s_%s_mainBlending_orientConstraint' % (self.chName, self.lastZone, controllerName, self.lastSide))

            ARCore.lockAndHideAttr(handFkControllerList[i], True, False, False)

            # connect to deform skeleton
            mainJoint.rename(str(handJoints[i]).replace('skin', 'main'))  # rename, useful for snap proxy model
            pm.orientConstraint(mainJoint, handJoints[i], maintainOffset=False, name='%s_%s_%s_%s_joint_orientConstraint' % (self.chName, self.lastZone, controllerName, self.lastSide))

            ## finger ##
            # main ik fk toes
            for i, mainJoint in enumerate(fingerMainJointsList):
                controllerName = fingerControllerNameList[i]

                # connect to deform skeleton, review: point constraint toes main. strange behaviour
                mainJoint.rename(str(fingerJoints[i]).replace('joint', 'ctr'))
                pm.orientConstraint(mainJoint, fingerJoints[i], maintainOffset=False,  name='%s_%s_%s_%s_joint_orientConstraint' % (self.chName, controllerName, zoneC, self.lastSide))
                pm.pointConstraint(mainJoint, fingerJoints[i], maintainOffset=False,  name='%s_%s_%s_%s_joint_pointConstraint' % (self.chName, controllerName, zoneC, self.lastSide))

                if '1' in controllerName:
                    for zeroJoint in fingerZeroJoints:
                        if controllerName[:-1] in str(zeroJoint):
                            # create null grp to snap proxy model
                            fingerProxyNull = pm.group(empty=True, name=str(zeroJoint).replace('joint', 'main'))
                            # copy transforms
                            pm.xform(fingerProxyNull, ws=True, m=pm.xform(zeroJoint, ws=True, q=True, m=True))
                            # find parent
                            fingerParent = mainJoint.firstParent()
                            fingerParent.addChild(fingerProxyNull)  # make child of parent of the finger
                            # useful for snap proxy model
                            pm.aimConstraint(mainJoint, fingerProxyNull, aimVector=(zeroJoint.translateX.get(),0,0), worldUpType='objectrotation', worldUpObject=str(handMainJointsList[-1]))
                            # orient constraint, joint to froxy null
                            pm.orientConstraint(fingerProxyNull, zeroJoint, maintainOffset=False)


            return handIkControllerList, handFkControllerList + fingerMainJointsList


    def clavicle_auto(self, zone='clavicle', *funcs):
        """
        This method should be called as a *arg for ikFkChain_auto.
        :return:
        """
        # TODO, detect parent from las ikFk chain
        fkColor = 14 if self.lastSide == 'left' else 29
        clavicleJoints = [point for point in pm.ls() if re.match('^%s.*%s.*%s.*(?!End)(?!0)(?!twist).*skin_joint$' % (self.chName, zone, self.lastSide), str(point))]
        clUpperArmJoint = clavicleJoints[-1].getChildren()[0]

        parent = self.ikFk_MainJointList[0].firstParent()  # get parent of the system

        parentChilds = [child for child in parent.listRelatives(c=True, type='transform') if (self.lastSide in str(child)) and (self.lastZone in str(child).lower()) and not ('pole' in str(child))]

        logger.debug('childs: %s' %parentChilds)

        # store clavicle main joints here
        clavicleMainList = []

        for joint in clavicleJoints:
            controllerName = str(joint).split('_')[3]
            # create controller shape
            clavicleController = self.create_controller(str(joint).replace('skin', 'fk').replace('joint', 'ctr'), '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
            pm.xform(clavicleController, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))
            clavicleMainList.append(clavicleController)

        # hierarchy
        parent.addChild(clavicleMainList[0])

        # swing controller
        clavicleSwingCrt = self.create_controller('%s_%s_%s_swing_fk_ctr' % (self.chName, zone, self.lastSide), 'swingFk_%s' % self.lastSide, 1, fkColor)
        pm.xform(clavicleSwingCrt, ws=True, m=pm.xform(clUpperArmJoint, q=True, ws=True, m=True))  # set transforms
        clavicleMainList[-1].addChild(clavicleSwingCrt)
        clavicleMainList.append(clavicleSwingCrt)

        # parent ikFk chains to swing
        for ctr in (parentChilds):
            clavicleSwingCrt.addChild(ctr)
        # swing visibility
        self.plusMinusIkFk.output1D.connect(clavicleSwingCrt.getShape().visibility)

        # create roots
        ARCore.createRoots(clavicleMainList)
        clavicleAutoGrpList = ARCore.createRoots(clavicleMainList, 'auto')

        # auto clavicle
        autoClavicleName = 'auto%s' % zone.capitalize()
        pm.addAttr(self.ikFkshape, longName=autoClavicleName, shortName=autoClavicleName, minValue=0.0, maxValue=1.0, type='float', defaultValue=0.3, k=True)
        # nodes drive rotation by influence
        clavicleMultiplyNode = pm.createNode('multiplyDivide', name='%s_%s_%s_multiply' % (self.chName, zone, self.lastSide))
        # todo: expose autoClavicle
        for axis in ('Y', 'Z'):
            # multiply by influence
            self.ikFkshape.attr(autoClavicleName).connect(clavicleMultiplyNode.attr('input1%s' % axis))
            self.ikFk_FkControllersList[0].attr('rotate%s' % axis).connect(clavicleMultiplyNode.attr('input2%s' % axis))
            # connect to auto clavicle
            clavicleMultiplyNode.attr('output%s' % axis).connect(clavicleAutoGrpList[0].attr('rotate%s' % axis))


        for i, joint in enumerate(clavicleJoints):
            # connect to deform joints
            #clavicleMainList[i].rename(str(joint).replace('joint','ctr'))  # rename for proxys sync
            pm.pointConstraint(clavicleMainList[i], joint, maintainOffset=False)
            pm.orientConstraint(clavicleMainList[i], joint, maintainOffset=True)

        # save data
        zoneSide = '%s_%s' % (zone, self.lastSide)
        #self.ikControllers[zone] = self.neckHeadIKCtrList
        self.fkControllers[zoneSide] = clavicleController
        return [], clavicleMainList

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
                clusterRoot = ARCore.createRoots([cluster])
        else:
            clusterRoot = ARCore.createRoots([cluster])

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
        controller = self.create_controller('%s_ctr' % str(cluster), controllerType, controllerSize, 24)
        # align with cluster, we need to query world space pivot
        controller.setTranslation(cluster.getPivots(ws=True)[0], 'world')
        #pm.xform(controller, ws=True, m=clusterMatrix)
        #parent
        parent.addChild(controller)
        # create root
        controllerRoot = ARCore.createRoots([controller])

        # connect controllr and cluster
        pm.parentConstraint(controller, cluster, maintainOffset=False, name='%s_parentConstraint' % str(cluster))
        ARCore.connectAttributes(controller, cluster, ['scale'], 'XYZ')

        return [controller], []

    def ikFkChain_wire(self, mesh, controllerType=None):
        """
        This method should be called as a *arg for ikFkChain_auto.
        Create a wire deformer and put in the hierarchy
        :return:
        """
        color = 7 if self.lastSide == 'left' else 5
        # create wire deformer
        wire, curve = ARCore.setWireDeformer(self.ikFk_MainJointList, mesh, '%s_%s_%s' % (self.chName, self.lastZone, self.lastSide))
        # Find base curve
        baseCurve = wire.baseWire[0].inputs()[0]
        # get controls
        curveTransforms = ARCore.TransformCurveCVCtr(curve)
        baseCurveTransforms = ARCore.TransformCurveCVCtr(baseCurve)

        # vinculate to rig
        for i, trn in enumerate(curveTransforms):
            self.ikFk_MainJointList[i].addChild(trn)
            self.ikFk_MainJointList[i].addChild(baseCurveTransforms[i])

            trn.rename('%s_%s_%s_wire_%s_drv' % (self.chName, self.lastZone, self.lastSide, i))
            if not (i == 0 or i == len(curveTransforms)-1):
                # createController
                if controllerType:
                    controller = self.create_controller('%s_%s_%s_wire_ctr' % (self.chName, self.lastZone, self.lastSide), controllerType, 2.0, color)
                else:
                    controller = pm.circle(nr=(1, 0, 0), r=5, name='%s_%s_%s_wire_ctr' % (self.chName, self.lastZone, self.lastSide))[0]
                    pm.delete(controller, ch=True)
                    controllerShape = controller.getShape()
                    controllerShape.overrideEnabled.set(True)
                    controllerShape.overrideColor.set(color)

                # align controller with point driver
                pm.xform(controller, ws=True, m=pm.xform(trn, q=True, ws=True, m=True))
                # parent controller
                self.ikFk_MainJointList[i].addChild(controller)
                controller.setRotation((0, 0, 0), 'object')
                controller.addChild(trn)  # child of the controller
                # create Roots
                ARCore.createRoots([controller])
                # lock and hide attributes
                ARCore.lockAndHideAttr(controller, False, True, True)

        # curves to no xform grp
        self.noXformGrp.addChild(curve.getTransform())
        curve.visibility.set(False)
        self.noXformGrp.addChild(baseCurve.getTransform())
        baseCurve.visibility.set(False)

        return [], []

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
        baseName = [self.chName, self.lastZone]
        if hasattr(self, 'lastSide'):
            # if it is the case, append to name
            baseName.append(self.lastSide)

        baseName.extend(['lattice', 'ctr'])
        controllerName = '_'.join(baseName)

        controller = self.create_controller(controllerName, 'pole', 1.8, 24)
        latticeList = ARCore.latticeBendDeformer(lattice, controller)

        # parent
        latticeList.append(latticeBase)
        pm.parent(latticeList, parent)

        # hide lattice
        latticeTransform.visibility.set(False)

        return [], []

    def PSSkirt_auto(self, zone, side, drivers, parent, offset=0.15, falloff=1, range=75):
        """
        TODO: less vector points, and more global
        :param zone:
        :param side:
        :param drivers:
        :param parent:
        :param offset:
        :param falloff:
        :param range:
        :return:
        """
        skirtJoints = [point for point in pm.ls() if re.match('^%s.*(%s).*%s.*joint$' % (self.chName, zone, side), str(point))]

        # get drivers positions
        driversPos = []
        for driver in drivers:
            driversPos.append(pm.xform(driver, ws=True, q=True, t=True))
        # arrange lists by hierarchy
        skirtJointsArrange = ARCore.arrangeListByHierarchy(skirtJoints)

        # create controllers
        fkControllerList = []  # fk controllers
        pointControllers = []  # point controllers
        for chainJoints in skirtJointsArrange:
            fkChainController=[]
            pointChainController=[]
            for joint in chainJoints:
                controller = self.create_controller(str(joint).replace('joint', 'ctr').replace('skin', 'fk'), 'squareFk', 1, 11)
                pm.xform(controller, ws=True, m=pm.xform(joint, ws=True, q=True, m=True))
                # construct hierarchy
                if fkChainController:
                    fkChainController[-1].addChild(controller)
                else:
                    parent.addChild(controller)  # if first, parent to parent, hips
                # append controller
                fkChainController.append(controller)

                # create point ctr
                pointCtr = self.create_controller(str(controller).replace('ctr', 'ctr').replace('fk', 'point'), 'pole', .5, 7)
                pm.xform(pointCtr, ws=True, m=pm.xform(controller, ws=True, q=True, m=True))
                # make shapes visibles review

                # parent to controller
                controller.addChild(pointCtr)
                # append point ctr
                pointChainController.append(pointCtr)

            # append fk list
            fkControllerList.append(fkChainController)
            pointControllers.append(pointChainController)

        # create roots
        rootsControllerList = []
        for fkCtrChain in  fkControllerList:
            ARCore.createRoots(fkCtrChain)
            rootsControllers = ARCore.createRoots(fkCtrChain, 'auto')
            rootsControllerList.append(rootsControllers)

        # create driven Vectors
        drivenObj=[]
        for joints in skirtJointsArrange:
            drivVec = pm.group(empty=True)
            pm.xform(drivVec, ws=True, m=pm.xform(joints[0], q=True, ws=True, m=True))
            drivVecPos = drivVec.getTranslation('world')
            drivVec.setTranslation([drivVecPos[0], driversPos[0][1], drivVecPos[2]], 'world')
            # point constraint, Review performance point vs matrix dot product
            parent.addChild(drivVec)
            drivenObj.append(drivVec)

        # create dot space
        driversRangeList=[]  # outputs of the dot system
        for driver in drivers:
            driverVectorName = '%s_driverVector' % (str(driver))
            try:
                # find a previous driver node created for the driver
                driverVector = pm.PyNode(driverVectorName)
            except:
                # if not, create
                # and use the object space translation as vector, normalized
                # to get the driver vector, we query childs position
                driverPM = pm.PyNode(driver)  # create pm node
                driverVectorGrp = pm.group(empty=True, name='%s_vectorGrp' % str(driverPM))
                driverMatrix = pm.xform(driverPM, q=True, m=True, ws=True)
                driverMatrix = ARCore.orientToPlane(driverMatrix, 'zx')
                pm.xform(driverVectorGrp, ws=True, m=driverMatrix)

                # orient constraint
                pm.orientConstraint(driverPM, driverVectorGrp, maintainOffset=True)
                # get vector
                childDriver = driverPM.childAtIndex(0).getTranslation('object')
                childDriver = pm.datatypes.Vector(childDriver)
                driverVector = ARCore.getVectorFromMatrix(driverVectorGrp, childDriver)
                driverVector.rename(driverVectorName)

                # parent
                parent.addChild(driverVectorGrp)

            rangeNodesList = []
            for i, driven in enumerate(drivenObj):
                drivenVector = ARCore.getVectorBetweenTransforms(driver, driven)
                dotPS = ARCore.dotBasedPS(driverVector, drivenVector)
                # offset
                offsetNode = pm.createNode('addDoubleLinear')
                offsetNode.input2.set(offset)  # offset value
                dotPS.outputX.connect(offsetNode.input1)
                # create condition
                condition = pm.createNode('condition')
                condition.operation.set(2)  # greater than
                condition.secondTerm.set(0)
                offsetNode.output.connect(condition.colorIfTrueR)
                offsetNode.output.connect(condition.firstTerm)
                for axis in ('R', 'G', 'B'):
                    condition.attr('colorIfFalse%s' % axis).set(0)

                # power to control fallof
                power = pm.createNode('multiplyDivide')
                power.operation.set(3)  # set to power
                condition.outColorR.connect(power.input1X)
                power.input2X.set(falloff)  # Fallof create here some controller
                # multiply by the maximum value to config the range
                rangeMult = pm.createNode('multDoubleLinear')
                power.outputX.connect(rangeMult.input1)
                rangeMult.input2.set(range)  # range
                # auto multiplier
                multiplier = pm.createNode('multDoubleLinear')
                rangeMult.output.connect(multiplier.input1)
                multiplier.input2.set(1)

                # append
                rangeNodesList.append(multiplier)

            driversRangeList.append(rangeNodesList)


        if len(driversRangeList) == 1:
            for i, rootCtr in enumerate(rootsControllerList):
                # connect to skirt
                driversRangeList[0][i].output.connect(rootCtr[0].rotateZ)  # attribute variable?

        elif len(driversRangeList) == 2:
            for i, rootCtr in enumerate(rootsControllerList):
                # create blend color
                condition = pm.createNode('condition')
                condition.operation.set(2)  # greater than
                # connect condition
                driversRangeList[0][i].output.connect(condition.firstTerm)
                driversRangeList[0][i].output.connect(condition.colorIfTrueR)
                # second driver
                driversRangeList[1][i].output.connect(condition.secondTerm)
                driversRangeList[1][i].output.connect(condition.colorIfFalseR)
                # connect to transform
                condition.outColorR.connect(rootCtr[0].rotateZ)


        # view controller attribute and auto attribute
        # auto attribute
        if not parent.hasAttr('skirtAuto'):
            # create attr
            pm.addAttr(parent, longName='skirtAuto', shortName='skirtAuto', minValue=0.0,
                       type='float', defaultValue=1.0, k=True)
        # connect node
        for rangeNodesList in driversRangeList:
            for multNode in rangeNodesList:
                parent.skirtAuto.connect(multNode.input2)

        # connect visibility
        if not parent.hasAttr('skirtControllers'):
            # create attr
            pm.addAttr(parent, longName='skirtControllers', shortName='skirtControllers',
                       type='bool', defaultValue=True, k=False)
            pm.setAttr('%s.skirtControllers' % str(parent), channelBox=True)
        # connect node
        for fkChainctr in fkControllerList:
            for fkCtr in fkChainctr:
                parent.skirtControllers.connect(fkCtr.visibility)

        # conenct to joints
        for i, pointChanCtr in enumerate(pointControllers):
            for j, pointCtr in enumerate(pointChanCtr):
                pm.pointConstraint(pointCtr, skirtJointsArrange[i][j], maintainOffset=False)
                pm.orientConstraint(pointCtr, skirtJointsArrange[i][j], maintainOffset=False)


    def point_auto(self, zone, parent):
        """
        Create a simple point control for a joint
        :param zone: zone of the points (joints)
        :param parent: parent of the controllers
        :return:
        """
        pointJoints = [point for point in pm.ls() if re.match('^%s.*%s.*.*joint$' % (self.chName, zone), str(point))]

        # create controllers
        pointControllers = []
        for joint in pointJoints:
            controller = self.create_controller(str(joint).replace('joint', 'ctr'), 'pole', 2, 10)
            pm.xform(controller, ws=True, m=pm.xform(joint, ws=True, q=True, m=True))
            # hierarchy
            parent.addChild(controller)
            pointControllers.append(controller)

        # roots
        ARCore.createRoots(pointControllers)

        # conenct to joints
        for i, joint in enumerate(pointJoints):
            pm.pointConstraint(pointControllers[i], joint, maintainOffset=False)
            pm.orientConstraint(pointControllers[i], joint, maintainOffset=False)
            ARCore.connectAttributes(pointControllers[i], joint,['scale'], 'XYZ')



    def create_controller(self, name, controllerType, s=1.0, colorIndex=4):
        """
        Args:
            name: name of controller
            controllerType(str): from json controller types
        return:
            controller: pymel transformNode
            transformMatrix: stored position
        """
        controller = ARCore.createController(name, controllerType, self.chName, self.path, s, colorIndex)
        return controller