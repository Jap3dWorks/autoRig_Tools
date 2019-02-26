import pymel.core as pm
import re
from maya import OpenMaya

from ..ARCore import ARCore as ARC
from ..ARCore import ARHelper as ARH
from ARAutoRig_Abstract import _ARAutoRig_Abstract

import logging
logging.basicConfig()
logger = logging.getLogger('ARAutoRig_Body:')
logger.setLevel(logging.DEBUG)

# TODO: main Joints, naming pe. akona_foreArm_main. similar a joint name
# TODO: Name convention revision
# name convention:
# name_zone_side_function_extra_type:
# akona_spine_chest_IK_ctr
# akona_arm_left_foreArm_twist1_jnt

class ARAutoRig_Body(_ARAutoRig_Abstract):
    """
    Class to construct corporal rig
    """
    def __init__(self, chName, path):
        """
        autoRig class tools
        """
        # TODO: create node Module or chName_rig_grp transform node with messages attributes to store connections
        self.joints = {}  # store joints, I need this?
        self.ikControllers = {}
        self.fkControllers = {}

        # super class init
        super(ARAutoRig_Body, self).__init__(chName, path)

        # create Main ctr
        try:
            self.mainCtr = pm.PyNode('main_ctr')
            self._ctrGrp.addChild(self.mainCtr)
        except:
            self.mainCtr = self._create_controller('main_ctr', 'main', 1, 18)
            self._ctrGrp.addChild(self.mainCtr)

        # connect main scale to grp joints
        ARC.DGUtils.connectAttributes(self.mainCtr, pm.PyNode('joints_grp'), ['scale'], ['X', 'Y', 'Z'])


    # TODO: zone var in names
    def spine_auto(self, zone='spine', *funcs):
        """
        Auto create a character spine
        """
        baseName = zone
        # detect spine joints and their positions
        spineJoints = [point for point in pm.ls() if re.match('^%s.*%s$' % (zone, self._skinJointNaming), str(point))]
        positions = [point.getTranslation(space='world') for point in spineJoints]
        logger.debug('Spine joints: %s' % spineJoints)

        spineCurveTransform = pm.curve(ep=positions, name='%s_1_crv' % baseName)
        # parent to nXform grp
        noXformSpineGrp = pm.group(empty=True, name='noXform_%s_grp' % baseName)
        noXformSpineGrp.inheritsTransform.set(False)
        self._noXformGrp.addChild(noXformSpineGrp)
        noXformSpineGrp.addChild(spineCurveTransform)

        # curve shape node
        spineCurve = spineCurveTransform.getShape()

        #rebuildCurve
        pm.rebuildCurve(spineCurve, s=2, rpo=True, ch=False, rt=0, d=3, kt=0, kr=0)

        # review: test autoMethod
        ARC.snapCurveToPoints(spineJoints, spineCurve, 16, 0.01)

        #TODO: nameController variable
        # create locators and connect to curve CV's
        spineDrvList = []
        self._spineIKControllerList = []
        spineFKControllerList = []
        for n, point in enumerate(spineCurve.getCVs()):
            ctrType = 'hips' if n == 0 else 'chest' if n == spineCurve.numCVs() - 1 else 'spine%s' % n
            # create grp to manipulate the curve
            spineDriver = pm.group(name='%s_%s_Curve_drv' % (baseName, ctrType), empty=True)
            spineDriver.setTranslation(point)
            decomposeMatrix = pm.createNode('decomposeMatrix', name='%s_%s_decomposeMatrix' % (baseName, ctrType))
            spineDriver.worldMatrix[0].connect(decomposeMatrix.inputMatrix)
            decomposeMatrix.outputTranslate.connect(spineCurve.controlPoints[n])
            spineDrvList.append(spineDriver)

            # create controller and parent locator
            spineController = self._create_controller('%s_%s_1_ik_ctr' % (baseName, ctrType), '%sIk' % ctrType, 1, 17)
            logger.debug('spine controller: %s' % spineController)

            spineController.setTranslation(point)

            spineController.addChild(spineDriver)
            self._spineIKControllerList.append(spineController)

            # create FK controllers
            if n < 3:
                # first fk controller bigger
                fkCtrSize = 1.5 if len(spineFKControllerList) == 0 else 1
                spineFKController = self._create_controller('%s_%s_fk_ctr' % (baseName, n + 1), 'hipsFk', fkCtrSize, 4)
                spineFKController.setTranslation(point)
                spineFKControllerList.append(spineFKController)

                # Fk hierarchy
                if len(spineFKControllerList) > 1:
                    spineFKControllerList[n-1].addChild(spineFKController)
                    logger.debug('parent %s, child %s' % (spineFKControllerList[-1], spineFKController))

            # configure ctr hierarchy, valid for 5 ctrllers
            if n == 1:
                self._spineIKControllerList[0].addChild(spineController)
                spineFKControllerList[0].addChild(self._spineIKControllerList[0])
            # last iteration
            elif n == (spineCurve.numCVs()-1):
                spineController.addChild(self._spineIKControllerList[-2])
                spineFKControllerList[-1].addChild(spineController)

                # add 3th ik controller to hierarchy too
                spineFKControllerList[1].addChild(self._spineIKControllerList[2])
                self.mainCtr.addChild(spineFKControllerList[0])

        # create roots grp
        ARC.createRoots(spineFKControllerList)
        spineControllerRootsList = ARC.createRoots(self._spineIKControllerList)

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
            jointDriverGrp = pm.group(empty=True, name='%s_%s_drv%s_drv' % (baseName, jointNameSplit, n+1))
            # jointDriverGrp = pm.spaceLocator(name='%s_target' % str(joint))
            pointOnCurveInfo = pm.createNode('pointOnCurveInfo', name='%s_%s_drv%s_positionOnCurveInfo' % (baseName, jointNameSplit, n+1))
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
                ObjectUpVector = pm.group(empty=True, name='%s_%s_drv%s_upVector' % (baseName, jointNameSplit, n+1))
                # ObjectUpVector = pm.spaceLocator(name='%s_upVector' % str(joint))
                ObjectUpVector.setTranslation(jointDriverGrp.getTranslation() + pm.datatypes.Vector(0, 0, -20), 'world')
                noXformSpineGrp.addChild(ObjectUpVector)
                ObjectUpVectorList.append(ObjectUpVector)
                # if not last iteration index -1
                objUpVectorIndex = -2
            # AimConstraint locators, each locator aim to the upper locator
            if n == 0:
                # parent first ObjectUpVector, to hips controller
                self._spineIKControllerList[0].addChild(ObjectUpVector)
            else:
                aimConstraint = pm.aimConstraint(self.jointDriverList[-1], self.jointDriverList[-2], aimVector=(1,0,0), upVector=(0,1,0), worldUpType='object', worldUpObject=ObjectUpVectorList[objUpVectorIndex])


        # parent last target transform, to chest
        self._spineIKControllerList[-1].addChild(ObjectUpVectorList[-1])

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

            pointContraint = pm.pointConstraint(ObjectUpVectorList[-1], ObjectUpVectorList[0], upVectorObject, maintainOffset=False,
                                                name='%s_%s_drv_upVector_pointConstraint' % (baseName, jointNameSplit))
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
                spineIkCtrConstr = self._spineIKControllerList[min(n, len(self._spineIKControllerList) - 1)]
                spineIkCtrConstr.rename(str(joint).replace('joint', 'ctr').replace('skin','main'))  # rename ctr, useful for snap proxy model
                # constraint
                pm.pointConstraint(self.jointDriverList[n], joint, maintainOffset=False,  name='%s_%s_drv1_pointConstraint' % (baseName, jointNameSplit))
                endJointOrientConstraint = pm.orientConstraint(self._spineIKControllerList[min(n, len(self._spineIKControllerList) - 1)], joint, maintainOffset=True, name='%s_%s_drv1_orientConstraint' % (baseName, jointNameSplit))
                endJointOrientConstraint.interpType.set(0)

            else:
                # connect to deform joints
                self.jointDriverList[n].rename(str(joint).replace('skin', 'main'))  # rename driver, useful for snap proxy model
                pm.parentConstraint(self.jointDriverList[n], joint, maintainOffset=True, name='%s_%s_drv1_parentConstraint' % (baseName, jointNameSplit))

        # stretch
        ARH.stretchCurveVolume(spineCurve, spineJoints, baseName, self.mainCtr)

        # lock and hide attributes
        ARC.lockAndHideAttr(self._spineIKControllerList[1:-1], False, True, True)  # ik Ctr, no hips and chest
        ARC.lockAndHideAttr(spineFKControllerList[1:], True, False, True)  # fk controller list, no hips
        ARC.lockAndHideAttr(spineFKControllerList[0], False, False, True)  # fk controller hips
        ARC.lockAndHideAttr([self._spineIKControllerList[0], self._spineIKControllerList[-1]], False, False, True)  # ik Ctr, hips and chest

        # function for create extra content
        for func in funcs:
            ikControllers, fkControllers = func()
            #self.spineIKControllerList = self.spineIKControllerList + ikControllers
            #spineFKControllerList = spineFKControllerList + fkControllers

        # save data
        self.joints[zone] = spineJoints
        self.ikControllers[zone] = self._spineIKControllerList
        self.fkControllers[zone] = spineFKControllerList

        return self._spineIKControllerList, spineFKControllerList


    def neckHead_auto(self, zone='neckHead', *funcs):
        """
        Create neck head system.
        :param zone:
        :param funcs:
        :return:
        """
        self._lastZone = zone
        baseName = zone
        # store joints, not end joint
        neckHeadJoints = [point for point in pm.ls() if re.match('^%s.*%s$' % (zone, self._skinJointNaming), str(point))]
        logger.debug('Neck head joints: %s' % neckHeadJoints)
        positions = [point.getTranslation(space='world') for point in neckHeadJoints[:-1]]  # no tip joint

        neckHeadCurveTransform = pm.curve(ep=positions, name='%s1_crv' % baseName)
        # parent to noXform grp
        noXformNeckHeadGrp = pm.group(empty=True, name='%s_noXform_grp' % baseName)
        noXformNeckHeadGrp.inheritsTransform.set(False)
        self._noXformGrp.addChild(noXformNeckHeadGrp)
        noXformNeckHeadGrp.addChild(neckHeadCurveTransform)

        neckHeadCurve = neckHeadCurveTransform.getShape()

        # rebuildCurve
        pm.rebuildCurve(neckHeadCurve, s=2, rpo=True, ch=False, rt=0, d=3, kt=0, kr=0)
        ARC.snapCurveToPoints(neckHeadJoints[:-1], neckHeadCurve, 16, 0.01)

        # create locators and connect to curve CV's
        neckHeadDrvList = []
        self.neckHeadIKCtrList = []
        neckHeadFKCtrList = []

        for n, point in enumerate(neckHeadCurve.getCVs()):
            # create drivers to manipulate the curve
            neckHeadDriver = pm.group(name='%s_%s_curve_drv' % (baseName, n+1), empty=True)
            neckHeadDriver.setTranslation(point)
            # use the worldMatrix
            decomposeMatrix = pm.createNode('decomposeMatrix', name='%s_%s_decomposeMatrix' % (baseName, n+1))
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
                neckHeadIKCtr = self._create_controller('%s_%s_ik_ctr' % (baseName, ctrType), '%sIk' % ctrType, 1, 17)
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
                    neckHeadFKCtr = self._create_controller('%s_%s1_fk_ctr' % (baseName, ctrType), 'neckFk1', 1, 4)
                    neckHeadFKCtr.setTranslation(neckHeadJoints[0].getTranslation('world'), 'world')
                    neckHeadFKCtrList.append(neckHeadFKCtr)

                    neckHeadFKCtr2 = self._create_controller('%s_%s2_fk_ctr' % (baseName, ctrType), 'neckFk', 1, 4)
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
        self.neckHeadIKCtrList[-1].rename('%s_head_1_IK_ctr' % (baseName))  # review: better here or above?
        # Fk parent to last ik spine controller
        self.ikControllers['spine'][-1].addChild(neckHeadFKCtrList[0])

        # create roots grp
        neckHeadFKCtrRoots = ARC.createRoots(neckHeadFKCtrList)
        neckHeadIKCtrRoots = ARC.createRoots(self.neckHeadIKCtrList)

        # head orient auto, isolate
        # head orient neck grp
        neckOrientAuto = pm.group(empty=True, name='%s_head_orientAuto_1_grp' % baseName)
        neckOrientAuto.setTranslation(self.neckHeadIKCtrList[-1].getTranslation('world'), 'world')
        neckHeadFKCtrList[-1].addChild(neckOrientAuto)

        headIkAutoGrp = pm.group(empty=True, name='%s_head_orientAuto_ikAuto_1_grp' % baseName)
        headIkAutoGrp.setTranslation(self.neckHeadIKCtrList[-1].getTranslation('world'), 'world')
        neckHeadFKCtrList[-1].addChild(headIkAutoGrp)
        headIkAutoGrp.addChild(neckHeadIKCtrRoots[-1])

        # head orient base grp
        baseOrientAuto = pm.group(empty=True, name='%s_orientAuto_head_base_1_grp' % baseName)
        baseOrientAuto.setTranslation(neckOrientAuto.getTranslation('world'), 'world')
        self.mainCtr.addChild(baseOrientAuto)

        # create driver attr
        pm.addAttr(self.neckHeadIKCtrList[-1], longName='isolateOrient', shortName='isolateOrient', minValue=0.0,
                   maxValue=1.0, type='float', defaultValue=0.0, k=True)
        pm.addAttr(self.neckHeadIKCtrList[-1], longName='isolatePoint', shortName='isolatePoint', minValue=0.0,
                   maxValue=1.0, type='float', defaultValue=0.0, k=True)

        # constraint head controller offset to orient auto grps
        autoOrientConstraint = pm.orientConstraint(baseOrientAuto, neckOrientAuto, headIkAutoGrp, maintainOffset=False,
                                                   name='%s_head_autoOrient_1_orientConstraint' % baseName)
        autoPointConstraint = pm.pointConstraint(baseOrientAuto, neckOrientAuto, headIkAutoGrp, maintainOffset=False,
                                                 name='%s_head_autoOrient_1_pointConstraint' % baseName)

        # create Nodes and connect
        self.neckHeadIKCtrList[-1].isolateOrient.connect(autoOrientConstraint.attr('%sW0' % str(baseOrientAuto)))
        self.neckHeadIKCtrList[-1].isolatePoint.connect(autoPointConstraint.attr('%sW0' % str(baseOrientAuto)))

        plusMinusAverageOrient = pm.createNode('plusMinusAverage', name='%s_head_orientAuto_isolateOrient_1_PMA' % baseName)
        plusMinusAveragepoint = pm.createNode('plusMinusAverage', name='%s_head_pointAuto_isolateOrient_1_PMA' % baseName)
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
            jntNameSplt = str(joint).split('_')[1]
            jointDriverGrp = pm.group(empty=True, name='%s_%s_drv%s_drv' % (baseName, jntNameSplt, n+1))
            # jointDriverGrp = pm.spaceLocator(name='%s_target' % str(joint))
            pointOnCurveInfo = pm.createNode('pointOnCurveInfo', name='%s_%s_drv%s_positionOnCurveInfo' % (baseName, jntNameSplt, n+1))
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
                                                maintainOffset=False, name='%s_%s_upVector_drv_pointConstraint' % (baseName, jntNameSplt))
            pointContraint.attr('%sW0' % str(ObjectUpVectorList[-1])).set(pointConstraintFactor)
            pointContraint.attr('%sW1' % str(ObjectUpVectorList[0])).set(1 - pointConstraintFactor)

        for n, joint in enumerate(neckHeadJoints):
            # for each joint, create a multiply divide node
            # formula for scale: 1+(factorScale - 1)*influence
            # if is an end joint, do nothing
            # TODO: change Tip by end
            if 'Tip' in str(joint):
                continue

            jntNameSplt = str(joint).split('_')[1]
            # Constraint for the head zone
            # be careful with naming, this should be more procedural
            if '_head' in str(joint):
                # head joint, with point to driver, and orient to controller
                pm.pointConstraint(self.neckHeadJointDriverList[n], joint, maintainOffset=False, name='%s_%s_1_drv_pointConstraint' % (baseName, jntNameSplt))
                # orient to controller
                self.neckHeadIKCtrList[-1].rename(str(joint).replace('skin', 'ctr'))  # rename, useful for snap proxy model
                pm.orientConstraint(self.neckHeadIKCtrList[-1], joint, maintainOffset=True, name='%s_%s_1_drv_orientConstraint' % (baseName, jntNameSplt))
                # connect scales
                ARC.DGUtils.connectAttributes(self.neckHeadIKCtrList[-1], joint, ['scale'], 'XYZ')

            else:
                self.neckHeadJointDriverList[n].rename(str(joint).replace('skin', 'main'))  # rename, useful for snap proxy model
                pm.parentConstraint(self.neckHeadJointDriverList[n], joint, maintainOffset=True, name='%s_%s_1_drv_parentConstraint' % (baseName, jntNameSplt))

        # stretch
        ARH.stretchCurveVolume(neckHeadCurve, neckHeadJoints[:-1], baseName, self.mainCtr)

        # freeze and hide attributes.
        ARC.lockAndHideAttr(neckHeadFKCtrList, False, False, True)
        # lock and hide neck attr, it's here because we have only one
        ARC.lockAndHideAttr(self.neckHeadIKCtrList[0], False, True, True)

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
        baseName = "%s_%s" % (zone, side)
        twistName = "twist"

        zoneA = zone
        self._lastZone = zone
        self._lastSide = side
        fkColor = 14 if side == 'left' else 29

        # be careful with poseInterpolator
        # try a finder with the API
        ikFkJoints = [point for point in pm.ls() if re.match('^%s.*%s_.*?_(skin_joint)$' % (zoneA, side), str(point).lower()) and not twistName in str(point)]
        self.ikFkTwistJoints = [point for point in pm.ls() if re.match('^%s.*%s.*(twist).*(skin_joint)$' % (zoneA, side), str(point).lower())]
        logger.debug('%s %s joints: %s' % (side, zoneA, ikFkJoints))
        logger.debug('%s %s twist joints: %s' % (side, zoneA, self.ikFkTwistJoints))

        # group for ikFk controls
        self.ikFkCtrGrp = pm.group(empty=True, name='%s_ik_ctrGrp_root' % baseName)
        self.mainCtr.addChild(self.ikFkCtrGrp)

        # sync ikFkTwistJoints index with ikFk joints index
        ikFkTwistSyncJoints = ARC.syncListsByKeyword(ikFkJoints, self.ikFkTwistJoints, twistName)

        # fk controllers are copies of ikFk joints
        # save controllers name
        self._ikFk_FkControllersList = []
        self._ikFk_IkControllerList = []
        self._ikFk_MainJointList = []
        ikFkTwistList = []
        self._ikFk_IkJointList = []

        NameIdList = []  # store idNames. p.e upperLeg, lowerLeg

        # duplicate joints
        # todo: no i variable
        for n, joint in enumerate(ikFkJoints):
            controllerName = str(joint).split('_')[-3] if 'end' not in str(joint) else 'end'  # if is an end joint, rename end
            # fk controllers, last joint is an end joint, it doesn't has controller on the json controller file,
            # so tryCatch should give an error
            try:
                # review this, use a check, not a try
                fkControl = self._create_controller('%s_%s_fk_ctr' % (baseName, controllerName), '%sFk_%s' % (controllerName, side), 1, fkColor)
                pm.xform(fkControl, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))
                self._ikFk_FkControllersList.append(fkControl)
            except:
                logger.debug('no controller for fk controller: %s' % joint)
                pass
            # ik and main joints
            self._ikFk_IkJointList.append(joint.duplicate(po=True, name='%s_%s_ik_joint' % (baseName, controllerName))[0])
            self._ikFk_MainJointList.append(joint.duplicate(po=True, name='%s_%s_main_joint' % (baseName, controllerName))[0])

            ### twist Joints ####
            if ikFkTwistSyncJoints[n]:
                ikFkTwistIni = [joint.duplicate(po=True, name='%s_%s_%s0_joint' % (baseName, controllerName, twistName))[0]]

                for j, twstJnt in enumerate(ikFkTwistSyncJoints[n]):
                    # duplicate and construc hierarchy
                    ikFkTwistIni.append(twstJnt.duplicate(po=True, name='%s_%s_%s%s_joint' % (baseName, controllerName, twistName, j+1))[0])
                    ikFkTwistIni[-2].addChild(ikFkTwistIni[-1])

                ikFkTwistList.append(ikFkTwistIni)  # append to list of tJoints
                self.mainCtr.addChild(ikFkTwistIni[0])

                # parent twist joints
                if n == 0:
                    parent.addChild(ikFkTwistIni[0])  # first to ctr ik hips
                else:
                    self._ikFk_MainJointList[-2].addChild(ikFkTwistIni[0])  # lower twist child of upper ikFk

                # create twist group orient tracker, if is chain before foot or hand, track foot or hand
                if ikFkTwistSyncJoints[n] == ikFkTwistSyncJoints[-2]:  # just before end joint
                    # This twist joints will be drive by another system, foot or hand in general, so we store the
                    # necessary info in some class attributes.
                    self.footTwstList = list(ikFkTwistIni)
                    self.footTwstZone = zoneA
                    self.footTwstCtrName = controllerName
                    self.footpointCnstr = self._ikFk_MainJointList[-1]

                else:
                    # connect and setup ikFk Twist Ini chain
                    ARH.twistJointsConnect(ikFkTwistIni, self._ikFk_MainJointList[-1], '%s_%s' % (baseName, controllerName))

            NameIdList.append(controllerName)

        logger.debug('ikFk IK joints: %s' % self._ikFk_IkJointList)

        # reconstruct hierarchy
        # create Fk control shapes
        for i, fkCtr in enumerate(self._ikFk_FkControllersList):  # last joint does not has shape
            # ik hierarchy
            self._ikFk_IkJointList[i].addChild(self._ikFk_IkJointList[i + 1])
            # main hierarchy
            self._ikFk_MainJointList[i].addChild(self._ikFk_MainJointList[i + 1])
            # last it avoid this
            # fk controls
            if i != len(self._ikFk_FkControllersList)-1:
                fkCtr.addChild(self._ikFk_FkControllersList[i + 1])

        # ik control
        self.ikFk_IkControl = self._create_controller("%s_ik_ctr" % baseName, "%sIk_%s" % (zoneA, side), 1, 17)
        self.ikFk_IkControl.setTranslation(ikFkJoints[-1].getTranslation('world'), 'world')
        self.ikFkCtrGrp.addChild(self.ikFk_IkControl)  # parent to ctr group

        # set hierarchy
        parent.addChild(self._ikFk_FkControllersList[0])
        parent.addChild(self._ikFk_MainJointList[0])
        parent.addChild(self._ikFk_IkJointList[0])

        # save to list
        self._ikFk_IkControllerList.append(self.ikFk_IkControl)
        ARC.createRoots(self._ikFk_IkControllerList)

        # fkRoots
        self.ikFk_FkCtrRoots = ARC.createRoots(self._ikFk_FkControllersList)
        ARC.createRoots(self._ikFk_FkControllersList, 'auto')

        # set preferred angle
        self._ikFk_IkJointList[1].preferredAngleZ.set(-15)
        # ik solver
        ikHandle, ikEffector = pm.ikHandle(startJoint=self._ikFk_IkJointList[0], endEffector=self._ikFk_IkJointList[-1], solver='ikRPsolver', name='%s_ik_handle' % baseName)
        ikEffector.rename('%s_ik_effector' % baseName)
        self.ikFk_IkControl.addChild(ikHandle)
        # create poles
        ikFkPoleController = self._create_controller('%s_pole_ik_ctr' % baseName, "pole", 2)
        ARC.relocatePole(ikFkPoleController, self._ikFk_IkJointList, 35)  # relocate pole Vector
        self.ikFkCtrGrp.addChild(ikFkPoleController)
        pm.addAttr(ikFkPoleController, ln='polePosition', at='enum', en="world:root:foot", k=True)
        # save poleVector
        self._ikFk_IkControllerList.append(ikFkPoleController)

        # constraint poleVector
        pm.poleVectorConstraint(ikFkPoleController, ikHandle)

        # root poleVector
        ikFkPoleVectorAuto = ARC.createRoots([ikFkPoleController])
        ARC.createRoots([ikFkPoleController])

        # TODO: more abstract
        # poleVectorAttributes
        poleAttrgrp=[]
        ikFkPoleAnimNodes=[]
        for attr in ('world', 'root', zoneA):
            ikFkPoleGrp = pm.group(empty=True, name="%s_%s_ik_pole_grp" % (baseName, attr.capitalize()))
            poleAttrgrp.append(ikFkPoleGrp)
            pm.xform(ikFkPoleGrp, ws=True, m=pm.xform(ikFkPoleVectorAuto, ws=True, m=True, q=True))
            ikFkPoleAnim = pm.createNode('animCurveTU', name='%s_%s_ik_pole_animNode' % (baseName, attr.capitalize()))
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
        ikFkNode = pm.spaceLocator(name='%s_attr' % baseName)
        self.ikFkshape = ikFkNode.getShape()
        self.ikFkshape.visibility.set(0)
        pm.addAttr(self.ikFkshape, longName='ikFk', shortName='ikFk', minValue=0.0, maxValue=1.0, type='float', defaultValue=1.0, k=True)
        # hide unused attributes
        for attr in ('localPosition', 'localScale'):
            for axis in ('X', 'Y', 'Z'):
                pm.setAttr('%s.%s%s' % (self.ikFkshape, attr, axis), channelBox=False, keyable=False)

        self.plusMinusIkFk = pm.createNode('plusMinusAverage', name='%s_ikFk_blending_pma' % baseName)
        self.ikFkshape.ikFk.connect(self.plusMinusIkFk.input1D[1])
        self.plusMinusIkFk.input1D[0].set(1)
        self.plusMinusIkFk.operation.set(2)

        if stretch:
            ###Strech###
            # fk strech
            # review this part, it could be cool only one func
            ikFk_MainDistances, ikFk_MaxiumDistance = ARC.calcDistances(self._ikFk_MainJointList)  # review:  legIkJointList[0]   legIkCtrRoot
            #ikFkStretchSetup
            ARH.stretchIkFkSetup(self.ikFk_FkCtrRoots[1:], ikFk_MainDistances, self.ikFkshape, [self._ikFk_IkJointList[0], ikHandle],
                                 ikFk_MaxiumDistance, self._ikFk_IkJointList[1:], self._ikFk_MainJointList[1:], ikFkTwistList, baseName, self.mainCtr, ikFkPoleController)

        # iterate along main joints
        # blending
        # todo: visibility, connect to ikFkShape
        # last joint of mainJointList is a end joint, do not connect
        for i, joint in enumerate(self._ikFk_MainJointList[:-1]):
            # attributes
            orientConstraint = pm.orientConstraint(self._ikFk_IkJointList[i], self._ikFk_FkControllersList[i], joint, maintainOffset=False, name='%s_main_blending_orientConstraint' % baseName)
            self.ikFkshape.ikFk.connect(orientConstraint.attr('%sW0' % str(self._ikFk_IkJointList[i])))
            self.ikFkshape.ikFk.connect(self._ikFk_IkJointList[i].visibility)

            # parent shape
            self._ikFk_FkControllersList[i].addChild(self.ikFkshape, s=True, add=True)

            # conenct blendging node
            self.plusMinusIkFk.output1D.connect(orientConstraint.attr('%sW1' % str(self._ikFk_FkControllersList[i])))
            # review: visibility shape
            self.plusMinusIkFk.output1D.connect(self._ikFk_FkControllersList[i].visibility)

        # twist joints bending bones connect, if curve wire detected, no use bendingJoints
        # TODO: control by twist or wire?
        if ikFkTwistList:
            # if twist joints, we could desire bending controls or not
            if bendingBones:
                # todo: name args
                ARH.twistJointBendingBoneConnect(parent, self._ikFk_MainJointList, ikFkTwistList, ikFkJoints, ikFkTwistSyncJoints, self._chName, zone, side, NameIdList, self._path)
            else:
                ARH.twistJointConnect(self._ikFk_MainJointList, ikFkTwistList, ikFkJoints, ikFkTwistSyncJoints)

        # or connect the rig with not twist joints
        else:
            for i, joint in enumerate(self._ikFk_MainJointList):
                # connect to deform skeleton TODO: connect func, with rename options
                joint.rename(str(ikFkJoints[i]).replace('skin', 'main'))  # rename, useful for snap proxy model
                pm.orientConstraint(joint, ikFkJoints[i], maintainOffset=False, name='%s_main_parentConstraint' % baseName)
                pm.pointConstraint(joint, ikFkJoints[i], maintainOffset=False, name='%s_main_parentConstraint' % baseName)

        # ik blending controller attr
        self.ikFkshape.ikFk.connect(ikFkPoleController.visibility)
        self.ikFkshape.ikFk.connect(self.ikFk_IkControl.visibility)
        self.ikFk_IkControl.addChild(self.ikFkshape, add=True, s=True)

        # lock and hide attributes
        # lock and hide ik ctr scale attr
        ARC.lockAndHideAttr(self.ikFk_IkControl, False, False, True)
        ARC.lockAndHideAttr(self._ikFk_FkControllersList, True, False, True)
        ARC.lockAndHideAttr(ikFkPoleController, False, True, True)

        # function for create foots or hands
        for func in funcs:
            ikControllers, fkControllers = func()
            self._ikFk_IkControllerList = self._ikFk_IkControllerList + ikControllers
            self._ikFk_FkControllersList = self._ikFk_FkControllersList + fkControllers

        # save Data
        zoneSide = '%s_%s' % (zoneA, side)
        self.joints[zoneSide] = ikFkJoints
        self.ikControllers[zoneSide] = self._ikFk_IkControllerList
        self.fkControllers[zoneSide] = self._ikFk_FkControllersList

        # delete ikfkShape
        pm.delete(ikFkNode)

        return self._ikFk_IkControllerList, self._ikFk_FkControllersList


    def foot_auto(self, zones=('foot', 'toe'), planeAlign=None, *funcs):
        """
        # TODO: organize and optimize this Func
        This method should be called as a *arg for ikFkChain_auto.
        auto build a ik fk foot
        Args:
            side: left or right
            zone: foot
        """
        baseNameB = "%s_%s" % (zones[0], self._lastSide)
        baseNameLZ = "%s_%s" % (self._lastZone, self._lastSide)
        zoneB = zones[0]
        zoneC = zones[1]
        fkColor = 14 if self._lastSide == 'left' else 29
        toesJoints = [point for point in pm.ls() if re.match('^%s.*%s.*%s.(?!End)(?!0)(?!twist).*skin_joint$' % (zoneB, self._lastSide, zoneC), str(point))]
        #toesZeroJoints = [point for point in pm.ls() if re.match('^%s.*(%s).(?!_end)(?=0)(?!twist).*%s.*joint$' % (self.chName, zoneC, self.lastSide), str(point))]
        footJoints = [point for point in pm.ls() if re.match('^%s.*%s.*skin_joint$' % (zoneB, self._lastSide), str(point)) and not zoneC in str(point)]

        # arrange toes by joint chain p.e [[toea, toesa_Tip], [toeb, toeb_tip]]
        toesJointsArr = ARC.arrangeListByHierarchy(toesJoints)

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
            controllerName = str(joint).split('_')[-3]
            logger.debug('foot controller name: %s' % controllerName)
            footFkCtr = self._create_controller('%s_%s_fk_ctr' % (baseNameB, controllerName),
                                               '%sFk_%s' % (controllerName, self._lastSide), 1, fkColor)
            pm.xform(footFkCtr, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))

            footMain = joint.duplicate(po=True, name='%s_%s_main_joint' % (baseNameB, controllerName))[0]

            # get transformMatrix and orient new controller
            matrix = pm.xform(footFkCtr, ws=True, q=True, m=True)

            matrix = ARC.VectorMath.orientToPlane(matrix, planeAlign)  # adjusting orient to plane zx
            pm.xform(footFkCtr, ws=True, m=matrix)  # new transform matrix with vector adjust

            # fk control Shape
            shape = self._create_controller('%sShape' % str(footFkCtr), '%sFk_%s' % (controllerName, self._lastSide), 1, fkColor)
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
        fkControlChilds = self._ikFk_FkControllersList[-1].listRelatives(ad=True, type='transform')
        if fkControlChilds:
            fkControlChilds[0].addChild(footFkControllerList[0])
        else:
            self._ikFk_FkControllersList[-1].addChild(footFkControllerList[0])

        self._ikFk_MainJointList[-1].addChild(footMainJointsList[0])

        # twistJointsConnections
        if self.ikFkTwistJoints:
            ARH.twistJointsConnect(self.footTwstList, footMainJointsList[0], '%s_%s_%s_%s' % (self._chName, self.footTwstCtrName, self.footTwstZone, self._lastSide), self.footpointCnstr)

        # TODO: function from joint, ik, fk, main?
        # create toe Fk and ik ctr
        toeIkCtrParents = []  # list with first joint of toes chains
        toeMainParents = []
        for i, toe in enumerate(toesJointsArr):
            toeFkChain = []
            toeIkChain = []
            toeMainChain = []
            for joint in toe:
                controllerName = str(joint).split('_')[-3]
                logger.debug('foot controller name: %s' % controllerName)

                # create controllers and main
                toeFkCtr = self._create_controller('%s_%s_fk_ctr' % (baseNameB, controllerName), '%sFk_%s' % (controllerName, self._lastSide), 1, fkColor)
                pm.xform(toeFkCtr, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))

                toeMainJnt = joint.duplicate(po=True, name='%s_%s_main_joint' % (baseNameB, controllerName))[0]

                toeIkCtr = self._create_controller('%s_%s_ik_ctr' % (baseNameB, controllerName), '%sFk_%s' % (controllerName, self._lastSide), 1, fkColor)
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
        footIkCtr = self._create_controller('%s_foot_ik_ctr' % baseNameB, '%sIk_%s' % (zoneB, self._lastSide), 1, 17)
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
                    footIkCtrWalk = self._create_controller('%s_foot%s%s_ik_ctr' % (baseNameB, ctrType.capitalize(), inOut), 'foot%s%sIk_%s' % (ctrType.capitalize(), inOut, self._lastSide), 1, 17)
                    footIkControllerList[-1].addChild(footIkCtrWalk)
                    footIkCtr.attr('showControls').connect(footIkCtrWalk.getShape().visibility)
                    footIkControllerList.append(footIkCtrWalk)
            else:
                footIkCtrWalk = self._create_controller('%s_foot%s_ik_ctr' % (baseNameB, ctrType.capitalize()), 'foot%sIk_%s' % (ctrType.capitalize(), self._lastSide), 1, 17)
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
        footBallIkMatrix = pm.datatypes.Matrix([firstfootFkMatrix[0],
                                                firstfootFkMatrix[1],
                                                firstfootFkMatrix[2],
                                                [middleToeCtrMatrix[12], middleToeCtrMatrix[13], middleToeCtrMatrix[14], middleToeCtrMatrix[15]]])

        pm.xform(footBallIkCtr, ws=True, m=footBallIkMatrix)

        # parent toes Ik ctr to footToes
        logger.debug('toeIkCtrParents: %s' % toeIkCtrParents)
        for toeCtr in toeIkCtrParents:
            footToesIkCtr.addChild(toeCtr)

        # --end rest points--
        for i in self.ikFk_IkControl.listRelatives(c=True, type='transform'):  # traspase childs from previous leg controller
            footBallIkCtr.addChild(i)

        pm.delete(self.ikFk_IkControl.firstParent())  # if foot, we do not need this controller
        self._ikFk_IkControllerList.remove(self.ikFk_IkControl)

        # toes general Controller ik Fk review: no side review: ik ctrllers  simplyfy with for
        toeFkGeneralController = self._create_controller('%s_toeGeneral_fk_ctr' % baseNameB, 'toesFk', 1, fkColor)
        pm.xform(toeFkGeneralController, ws=True, m=middleToeCtrMatrix)  # align to middle individual toe review
        toeIkGeneralController = self._create_controller('%s_toeGeneral_ik_ctr' % baseNameB, 'toesFk', 1, fkColor)
        pm.xform(toeIkGeneralController, ws=True, m=middleToeCtrMatrix)
        # parent and store to lists
        footFkControllerList[-1].addChild(toeFkGeneralController)
        footToesIkCtr.addChild(toeIkGeneralController)
        toesFkControllerList.append(toeFkGeneralController)
        toesIkControllerList.append(toeIkGeneralController)

        # fk Roots and autos
        ARC.createRoots(footFkControllerList)
        ARC.createRoots(footFkControllerList, 'auto')
        ARC.createRoots(footIkControllerList)
        footRollAuto = ARC.createRoots(footFootRollCtr, 'footRollAuto')  # review: all in the same if
        footIkAuto = ARC.createRoots(footIkControllerList, 'auto')
        ARC.createRoots(toesFkControllerList)
        toesFkAuto = ARC.createRoots(toesFkControllerList, 'auto')
        ARC.createRoots(toesIkControllerList)
        toesIkAuto = ARC.createRoots(toesIkControllerList, 'auto')

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
                orientConstraint = pm.orientConstraint(footIkControllerList[-1], footFkControllerList[i], mainJoint, maintainOffset=True,
                                                       name='%s_%s_mainBlending_orientConstraint' % (baseNameB, controllerName))
                self.ikFkshape.ikFk.connect(orientConstraint.attr('%sW0' % str(footIkControllerList[-1])))  # shape with bleeding attribute
                self.ikFkshape.ikFk.connect(footIkControllerList[i].visibility)  # all foot chain visibility

                # parent ikFk shape
                footIkControllerList[0].addChild(self.ikFkshape, s=True, add=True)

                # parent ikFk shape
                footFkControllerList[0].addChild(self.ikFkshape, s=True, add=True)

                self.plusMinusIkFk.output1D.connect(orientConstraint.attr('%sW1' % str(footFkControllerList[i])))
                self.plusMinusIkFk.output1D.connect(footFkControllerList[i].getShape().visibility)

            else:
                pm.orientConstraint(footFkControllerList[i], mainJoint, maintainOffset=True, name='%s_%s_mainBlending_orientConstraint' % (baseNameB, controllerName))

            # connect to deform skeleton
            mainJoint.rename(str(footJoints[i]).replace('skin', 'main'))  # rename, useful for snap proxy model
            pm.orientConstraint(mainJoint, footJoints[i], maintainOffset=False, name='%s_%s_joint_orientConstraint' % (baseNameB, controllerName))

        ## TOES ##
        # main ik fk toes
        for i, mainJoint in enumerate(toesMainJointsList):
            controllerName = toeControllerNameList[i]
            # orient constraint only, if not, transitions from ik to fk are linear, and ugly
            orientConstraint = pm.orientConstraint(toesIkControllerList[i], toesFkControllerList[i], mainJoint, maintainOffset=True,
                                                   name='%s_%s_mainBlending_orientConstraint' % (baseNameB, controllerName))

            self.ikFkshape.ikFk.connect(orientConstraint.attr('%sW0' % str(toesIkControllerList[i])))  # shape with bleeding attribute
            self.ikFkshape.ikFk.connect(toesIkControllerList[i].visibility)  # all foot chain visibility

            self.plusMinusIkFk.output1D.connect(orientConstraint.attr('%sW1' % str(toesFkControllerList[i])))
            self.plusMinusIkFk.output1D.connect(toesFkControllerList[i].visibility)

            # connect to deform skeleton, review: point constraint toes main. strange behaviour
            mainJoint.rename(str(toesJoints[i]).replace('skin', 'main'))  # rename, useful for snap proxy model
            pm.orientConstraint(mainJoint, toesJoints[i], maintainOffset=False, name='%s_%s_joint_orientConstraint' % (baseNameLZ, controllerName))
            pm.pointConstraint(mainJoint, toesJoints[i], maintainOffset=False, name='%s_%s_joint_pointConstraint' % (baseNameLZ, controllerName))

        # total controllers
        footTotalFkControllers=footFkControllerList + toesFkControllerList

        # lock and hide attributes. after root creation
        ARC.lockAndHideAttr(footTotalFkControllers, True, False, True)   # fk controllers
        #ARCore.lockAndHideAttr(toesIkControllerList[-1], True, False, True)
        ARC.lockAndHideAttr(footIkControllerList[0], False, False, True)  # ik ctr foot
        ARC.lockAndHideAttr(footIkControllerList[1:], True, False, True)  # walk ik controllers
        ARC.lockAndHideAttr(toesIkControllerList, True, False, True)  # toes ik controllers


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
        baseNameB = "%s_%s" % (zones[0], self._lastSide)
        baseNameC = "%s_%s" % (zones[1], self._lastSide)
        baseNameLZ = "%s_%s" % (self._lastZone, self._lastSide)

        zoneB = zones[0]
        zoneC = zones[1]
        fkColor = 14 if self._lastSide == 'left' else 29  # review, more procedural
        # don't get zero joints, this do not has control
        fingerJoints = [point for point in pm.ls() if re.match('^%s.*%s.*%s.(?!End)(?!0)(?!twist).*skin_joint$' % (zoneB, self._lastSide, zoneC), str(point))]
        # here get zero joints, this do not has control
        fingerZeroJoints = [point for point in pm.ls() if re.match('^%s.*%s.*%s.(?!End)(?=0)(?!twist).*skin_joint$' % (zoneB, self._lastSide, zoneC), str(point))]
        # get hand joints
        handJoints = [point for point in pm.ls() if re.match('^%s.*%s.*((?!twist).).*skin_joint$' % (zoneB, self._lastSide), str(point)) and not zoneC in str(point)]

        # arrange toes by joint chain p.e [[toea, toesa_Tip], [toeb, toeb_tip]]
        fingerJointsArr = ARC.arrangeListByHierarchy(fingerJoints)
        logger.debug('Finger arranged list %s %s: %s' % (zoneB, self._lastSide, fingerJointsArr))

        # controllers and main lists
        handFkControllerList = []  # fk lists
        handIkControllerList = []  # ik lists
        handMainJointsList = []  # main lists
        fingerMainJointsList = []

        handControllerNameList = []
        fingerControllerNameList = []
        # create hand ctr
        for joint in handJoints:
            controllerName = str(joint).split('_')[-3]
            logger.debug('foot controller name: %s' % controllerName)
            handFkCtr = self._create_controller('%s_%s_fk_ctr' % (baseNameB, controllerName), '%sFk_%s' % (controllerName, self._lastSide), 1, fkColor)
            pm.xform(handFkCtr, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))

            handMain = joint.duplicate(po=True, name='%s_%s_main_joint' % (baseNameB, controllerName))[0]

            # get transformMatrix and orient new controller TODO: function
            matrix = pm.xform(handFkCtr, ws=True, q=True, m=True)

            matrix = ARC.VectorMath.orientToPlane(matrix, planeAlign)  # adjusting orient to plane zx
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
        fkControlChilds = self._ikFk_FkControllersList[-1].listRelatives(ad=True, type='transform')
        if fkControlChilds:
            fkControlChilds[0].addChild(handFkControllerList[0])
        else:
            self._ikFk_FkControllersList[-1].addChild(handFkControllerList[0])

        self._ikFk_MainJointList[-1].addChild(handMainJointsList[0])

        # twistJointsConnections
        if self.ikFkTwistJoints:
            ARH.twistJointsConnect(self.footTwstList, handMainJointsList[0],
                                      '%s_%s_%s_%s' % (self._chName, self.footTwstCtrName, self.footTwstZone, self._lastSide),
                                   self.footpointCnstr)

        # create finger Fk and ik ctr
        # last hand fkCtr, easiest access later
        fingerMainParents = []
        for i, toe in enumerate(fingerJointsArr):
            fingerMainChain = []
            for joint in toe:
                controllerName = str(joint).split('_')[-3]
                logger.debug('foot controller name: %s' % controllerName)
                # review
                fingerMainJnt = self._create_controller('%s_%s_fk_ctr' % (baseNameB, controllerName), '%sFk_%s' % (controllerName, self._lastSide), 1, fkColor)
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
        handIkCtr = self._create_controller('%s_hand_ik_ctr' % baseNameB, '%sIk_%s' % (zoneB, self._lastSide), 1, 17)
        self.ikFkCtrGrp.addChild(handIkCtr)
        handIkControllerList.append(handIkCtr)  # append joint to list

        for i in self.ikFk_IkControl.listRelatives(c=True, type='transform'):  # traspase childs from previous hand controller
            handIkCtr.addChild(i)

        pm.delete(self.ikFk_IkControl.firstParent())  # if foot, we do not need this controller
        self._ikFk_IkControllerList.remove(self.ikFk_IkControl)

        # fk Roots and autos
        ARC.createRoots(handFkControllerList)
        ARC.createRoots(handFkControllerList, 'auto')
        ARC.createRoots(handIkControllerList)
        footIkAuto = ARC.createRoots(handIkControllerList, 'auto')
        ARC.createRoots(fingerMainJointsList)
        toesIkAuto = ARC.createRoots(fingerMainJointsList, 'auto')

        ## BLEND ##
        # orient constraint main to ik or fk foot
        for i, mainJoint in enumerate(handMainJointsList):
            controllerName = handControllerNameList[i]
            if i == 0:
                # connect ik fk blend system, in a leg system only have one ik controller
                orientConstraint = pm.orientConstraint(handIkControllerList[-1], handFkControllerList[i], mainJoint, maintainOffset=True,
                                                       name="%s_%s_mainBlending_orientConstraint" % (baseNameLZ, controllerName))
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
                                    name='%s_%s_mainBlending_orientConstraint' % (baseNameLZ, controllerName))

            ARC.lockAndHideAttr(handFkControllerList[i], True, False, False)

            # connect to deform skeleton
            mainJoint.rename(str(handJoints[i]).replace('skin', 'main'))  # rename, useful for snap proxy model
            pm.orientConstraint(mainJoint, handJoints[i], maintainOffset=False, name='%s_%s_joint_orientConstraint' % (baseNameLZ, controllerName))

            ## finger ##
            # main ik fk toes
            for i, mainJoint in enumerate(fingerMainJointsList):
                controllerName = fingerControllerNameList[i]

                # connect to deform skeleton, review: point constraint toes main. strange behaviour
                mainJoint.rename(str(fingerJoints[i]).replace('joint', 'ctr'))
                pm.orientConstraint(mainJoint, fingerJoints[i], maintainOffset=False, name="%s_%s_joint_orientConstraint" % (baseNameC, controllerName))
                pm.pointConstraint(mainJoint, fingerJoints[i], maintainOffset=False, name="%s_%s_joint_pointConstraint" % (baseNameC, controllerName))

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
        baseName = "%s_%s" % (zone, self._lastSide)
        fkColor = 14 if self._lastSide == 'left' else 29
        clavicleJoints = [point for point in pm.ls() if re.match('^%s.*%s.*(?!End)(?!0)(?!twist).*skin_joint$' % (zone, self._lastSide), str(point))]
        clUpperArmJoint = clavicleJoints[-1].getChildren()[0]

        parent = self._ikFk_MainJointList[0].firstParent()  # get parent of the system

        parentChilds = [child for child in parent.listRelatives(c=True, type='transform') if (self._lastSide in str(child)) and (self._lastZone in str(child).lower()) and not ('pole' in str(child))]

        logger.debug('childs: %s' %parentChilds)

        # store clavicle main joints here
        clavicleMainList = []

        for joint in clavicleJoints:
            controllerName = str(joint).split('_')[-3]
            # create controller shape
            clavicleController = self._create_controller(str(joint).replace('skin', 'fk').replace('joint', 'ctr'), '%sFk_%s' % (controllerName, self._lastSide), 1, fkColor)
            pm.xform(clavicleController, ws=True, m=pm.xform(joint, q=True, ws=True, m=True))
            clavicleMainList.append(clavicleController)

        # hierarchy
        parent.addChild(clavicleMainList[0])

        # swing controller
        clavicleSwingCrt = self._create_controller('%s_swing_fk_ctr' % baseName, 'swingFk_%s' % self._lastSide, 1, fkColor)
        pm.xform(clavicleSwingCrt, ws=True, m=pm.xform(clUpperArmJoint, q=True, ws=True, m=True))  # set transforms
        clavicleMainList[-1].addChild(clavicleSwingCrt)
        clavicleMainList.append(clavicleSwingCrt)

        # parent ikFk chains to swing
        for ctr in (parentChilds):
            clavicleSwingCrt.addChild(ctr)
        # swing visibility
        self.plusMinusIkFk.output1D.connect(clavicleSwingCrt.getShape().visibility)

        # create roots
        ARC.createRoots(clavicleMainList)
        clavicleAutoGrpList = ARC.createRoots(clavicleMainList, 'auto')

        # auto clavicle
        autoClavicleName = 'auto%s' % zone.capitalize()
        pm.addAttr(self.ikFkshape, longName=autoClavicleName, shortName=autoClavicleName, minValue=0.0, maxValue=1.0, type='float', defaultValue=0.3, k=True)
        # nodes drive rotation by influence
        clavicleMultiplyNode = pm.createNode('multiplyDivide', name='%s_multiply' % baseName)
        # todo: expose autoClavicle
        for axis in ('Y', 'Z'):
            # multiply by influence
            self.ikFkshape.attr(autoClavicleName).connect(clavicleMultiplyNode.attr('input1%s' % axis))
            self._ikFk_FkControllersList[0].attr('rotate%s' % axis).connect(clavicleMultiplyNode.attr('input2%s' % axis))
            # connect to auto clavicle
            clavicleMultiplyNode.attr('output%s' % axis).connect(clavicleAutoGrpList[0].attr('rotate%s' % axis))


        for i, joint in enumerate(clavicleJoints):
            # connect to deform joints
            #clavicleMainList[i].rename(str(joint).replace('joint','ctr'))  # rename for proxys sync
            pm.pointConstraint(clavicleMainList[i], joint, maintainOffset=False)
            pm.orientConstraint(clavicleMainList[i], joint, maintainOffset=True)

        # save data
        zoneSide = '%s_%s' % (zone, self._lastSide)
        #self.ikControllers[zone] = self.neckHeadIKCtrList
        self.fkControllers[zoneSide] = clavicleController
        return [], clavicleMainList


    def ikFkChain_wire(self, mesh, controllerType=None):
        """
        This method should be called as a *arg for ikFkChain_auto.
        Create a wire deformer and put in the hierarchy
        :return:
        """
        baseName="%s_%s" % (self._lastZone, self._lastSide)
        color = 7 if self._lastSide == 'left' else 5
        # create wire deformer
        wire, curve = ARC.DeformerOp.setWireDeformer(self._ikFk_MainJointList, mesh, baseName)
        # Find base curve
        baseCurve = wire.baseWire[0].inputs()[0]
        # get controls
        curveTransforms = ARC.transformDriveNurbObjectCV(curve)
        baseCurveTransforms = ARC.transformDriveNurbObjectCV(baseCurve)

        # vinculate to rig
        for i, trn in enumerate(curveTransforms):
            self._ikFk_MainJointList[i].addChild(trn)
            self._ikFk_MainJointList[i].addChild(baseCurveTransforms[i])

            trn.rename('%s_wire_%s_drv' % (baseName, i))
            if not (i == 0 or i == len(curveTransforms)-1):
                # createController
                if controllerType:
                    controller = self._create_controller('%s_wire_ctr' % baseName, controllerType, 2.0, color)
                else:
                    controller = pm.circle(nr=(1, 0, 0), r=5, name='%s_wire_ctr' % baseName)[0]
                    pm.delete(controller, ch=True)
                    controllerShape = controller.getShape()
                    controllerShape.overrideEnabled.set(True)
                    controllerShape.overrideColor.set(color)

                # align controller with point driver
                pm.xform(controller, ws=True, m=pm.xform(trn, q=True, ws=True, m=True))
                # parent controller
                self._ikFk_MainJointList[i].addChild(controller)
                controller.setRotation((0, 0, 0), 'object')
                controller.addChild(trn)  # child of the controller
                # create Roots
                ARC.createRoots([controller])
                # lock and hide attributes
                ARC.lockAndHideAttr(controller, False, True, True)

        # curves to no xform grp
        self._noXformGrp.addChild(curve.getTransform())
        curve.visibility.set(False)
        self._noXformGrp.addChild(baseCurve.getTransform())
        baseCurve.visibility.set(False)

        # TODO: return controllers
        return [], []


    def PSSkirt_auto(self, zone, drivers, parent):
        """
        PoseSpace skirt
        TODO: Optimize -> use quat operations
        TODO: rename correctly
        :param zone:
        :param side:
        :param drivers:
        :param parent:
        :return:
        """
        # simplify names from modules
        VM_N = ARC.VectorMath_Nodes  # vector math for nodes module
        DGU = ARC.DGUtils  # dependency graph utils

        skirtJoints = [point for point in pm.ls() if re.match('^%s.*%s$' % (zone, self._skinJointNaming), str(point))]
        # arrange lists by hierarchy
        skirtJointsArrange = ARC.arrangeListByHierarchy(skirtJoints)

        # get drivers positions
        driversPos = []
        for driver in drivers:
            driversPos.append(pm.xform(driver, ws=True, q=True, t=True))

        # create controllers
        fkControllerList = []  # fk controllers
        pointControllers = []  # point controllers
        for chainJoints in skirtJointsArrange:
            fkChainController=[]
            pointChainController=[]
            for joint in chainJoints:
                controller = self._create_controller(str(joint).replace('joint', 'ctr').replace('skin', 'fk'), 'squareFk', 1, 11)
                pm.xform(controller, ws=True, m=pm.xform(joint, ws=True, q=True, m=True))
                # construct hierarchy
                if fkChainController:
                    fkChainController[-1].addChild(controller)
                else:
                    parent.addChild(controller)  # if first, parent to parent, hips
                # append controller
                fkChainController.append(controller)

                # create point ctr
                pointCtr = self._create_controller(str(controller).replace('ctr', 'ctr').replace('fk', 'point'), 'pole', 0.5, 7)
                pm.xform(pointCtr, ws=True, m=pm.xform(controller, ws=True, q=True, m=True))

                # parent to controller
                controller.addChild(pointCtr)
                # append point ctr
                pointChainController.append(pointCtr)

            # append fk list
            fkControllerList.append(fkChainController)
            pointControllers.append(pointChainController)

        # create roots
        firstChainRoot = []
        for fkCtrChain in fkControllerList:
            root = ARC.createRoots(fkCtrChain)
            firstChainRoot.append(root[0])

        driverVectors_list = []  # node with aligned x vector of the driver
        autoGrpTotal_list = []
        vRefGrpTotal_list = []
        lastNoTwistRef_grp = None
        # create driver matrix
        for drvId, driver in enumerate(drivers):
            DVName = '%s_system' % (str(driver))
            # and use the object space translation as vector, normalized
            driver = pm.PyNode(driver)  # create pm node

            # we do not use the driver itself to preserve modularity
            driverVectorGrp = pm.group(empty=True, name='%s_vectorGrp' % str(driver))  # <-this node x axis should control the system
            # get the matrix of the driver
            driverMatrix = pm.xform(driver, q=True, m=True, ws=True)
            pm.xform(driverVectorGrp, ws=True, m=driverMatrix)  # align with the driver object
            parent.addChild(driverVectorGrp)  # parent

            # use a copy of the vector matrix to calculate de dots.
            noTwistRef_grp = driverVectorGrp.duplicate()[0]  # <- we extract the dot vectors from this matrix
            noTwistRef_grp.rename('%s_refGrp' % str(driver))
            # orient constraint, and it should follow the driver object
            pm.orientConstraint(driver, driverVectorGrp, maintainOffset=False)

            # get vector
            # to get the driver vector, we query child position.
            childDriver = pm.datatypes.Vector(driver.childAtIndex(0).getTranslation('object'))
            invertDot = 1
            for axis in 'xyz':
                if int(getattr(childDriver, axis)):
                    # save this value, will be useful later to invert dot vector mask
                    invertDot = getattr(childDriver, axis) / abs(getattr(childDriver, axis))
                # abssolute value, needed to extract correctly the vector from the matrix
                setattr(childDriver, axis, abs(int(getattr(childDriver, axis))))

            # get vector from matrix, x vector in this case, cause childDriver has only x translate
            driverVector = VM_N.vectorProduct(childDriver, None, 3, "%s.worldMatrix[0]" % str(driverVectorGrp), True)  # <- X Axis
            logger.debug('Skirt driver Vector X: %s' % str(driverVector.get()))
            logger.debug(childDriver.x + childDriver.y + childDriver.z)

            # node with driverVector
            driverVector.node().rename('%s_driver' % DVName)
            driverVectors_list.append(driverVector.node())

            planeVecs = []
            for i, axis in enumerate('xyz'):
                # get the two vectors in object space that define the plane p.e: (0,1,0) or (0,0,1)
                # use int, because sometimes maya adds very low decimals, this is a way to avoid them
                if int(getattr(childDriver, axis)) == 0:  # Equal to zero. is one of the pair of vectors that define a plane
                    vector = pm.datatypes.Vector()
                    setattr(vector, axis, 1)
                    logger.debug('PSSkirt vector: %s %s' % (axis, vector))
                    planeVecs.append(vector)

            logger.debug('PSSkirt plane vectors: %s' % planeVecs)

            ## no twist transform track##
            # create a transform node that will follow the driven but its twist
            # we reconstruct transform matrix for that porpoise
            # first axis info
            refVectorY = VM_N.vectorProduct(planeVecs[0], None, 3, "%s.worldMatrix[0]" % str(noTwistRef_grp), False)
            vectorY_Proj = VM_N.projectVectorOntoPlane(refVectorY, driverVector, True)

            # second axis info
            refVectorZ = VM_N.vectorProduct(planeVecs[1],None,3, "%s.worldMatrix[0]" % str(noTwistRef_grp), False)
            vectorZ_Proj = VM_N.projectVectorOntoPlane(refVectorZ, driverVector, True)

            # x axis, useful later, for calculate de blend dot product
            refVectorX = VM_N.vectorProduct(childDriver, None, 3, "%s.worldMatrix[0]" % str(noTwistRef_grp), True)

            # get vector dot products for z and y
            # review:
            vecProd_list = DGU.treeTracker(vectorZ_Proj.node(), 'vectorProduct', True, 4)  # search for vectorProducts
            dotZ_node = [node for node in vecProd_list if node.operation.get() == 1][0]  # save here dot Node
            vecProd_list = DGU.treeTracker(vectorY_Proj.node(), 'vectorProduct', True, 4)
            dotY_node = [node for node in vecProd_list if node.operation.get() == 1][0]
            # get the abs Val of one dot product
            dotBlendAbs = VM_N.absVal(dotZ_node.outputX)

            # reconstruct vectors with cross product
            ZVer_crossY = VM_N.crossProduct(vectorZ_Proj, driverVector, True)

            YVer_crossZ = VM_N.crossProduct(driverVector, vectorY_Proj, True)

            # blend nodes, Z
            blendZ = pm.createNode('blendColors')
            dotBlendAbs.connect(blendZ.blender)
            YVer_crossZ.connect(blendZ.color1)
            vectorZ_Proj.connect(blendZ.color2)
            # Y
            blendY = pm.createNode('blendColors')
            dotBlendAbs.connect(blendY.blender)
            vectorY_Proj.connect(blendY.color1)
            ZVer_crossY.connect(blendY.color2)

            noTwistMatrix = VM_N.matrix4by4(driverVector, blendY.output, blendZ.output)
            # ref group
            # prepare matrix to blend between
            if autoGrpTotal_list:
                offsetMatrix = VM_N.matrixMult(noTwistRef_grp.worldMatrix[0], lastNoTwistRef_grp.worldInverseMatrix[0])
                noTwistMatrix = VM_N.matrixMult(offsetMatrix, noTwistMatrix)
                refNoOrientMatrix = VM_N.matrixMult(offsetMatrix, noTwistRef_grp.worldMatrix[0])
            else:
                refNoOrientMatrix = noTwistRef_grp.worldMatrix[0]

            # ref no twist orient matrix inv
            # this is the matrix for position 0
            noTwistMatrix = VM_N.matrixMult(noTwistMatrix, parent.worldInverseMatrix[0])
            refNoOrientMatrix = VM_N.matrixMult(refNoOrientMatrix, parent.worldInverseMatrix[0])

            # use quat operations to blend between rotations
            noTwistQuat = VM_N.matrixDecompose(noTwistMatrix)[0]
            noTwistQuat.node().rename("%s_noTwistQuat" % (str(driver)))
            refNoOrientQuat = VM_N.matrixDecompose(refNoOrientMatrix)[0]

            # vector mask
            # the projection of the driver over the ref plane, and normalized, we will use this to set the level
            # of influence for each driver
            maskDotVDirection = VM_N.multiplyDivive(driverVector, [invertDot, invertDot, invertDot], 1)  # invert if necessary
            # save plug
            maskDotVector = VM_N.projectVectorOntoPlane(maskDotVDirection, refVectorX, True)
            maskDotVector.node().rename(str(driver)+"_projectedVector")

            # get notwist grp world space translation
            noTwistGrpTrans_plug = VM_N.vectorProduct([0, 0, 0], None, 4, "%s.worldMatrix[0]" % str(noTwistRef_grp), False)  # world space trans
            ##connect with controllers##
            # for each root, create a auto root
            # connect with no twist grp, using dot product to evaluate the weight for each auto
            for i, root in enumerate(firstChainRoot):
                # create auto grp, with no twist grp orient
                if not lastNoTwistRef_grp:
                    autoGrp = pm.group(empty=True, name='%s_auto' % str(root))
                    pm.xform(autoGrp, ws=True, m=driverMatrix)  # get orient from ref
                    autoGrp.setTranslation(root.getTranslation('world'), 'world')  # get position from root
                    parent.addChild(autoGrp)
                    autoGrp.addChild(root)  # root as a child of the new auto
                    # save aturoGrp
                    autoGrpTotal_list.append(autoGrp)

                    # create a ref grp
                    refGrp = autoGrp.duplicate(po=True, name=str(autoGrp).replace("auto", "vRef"))[0]
                    vRefGrpTotal_list.append(refGrp)

                # get autogrp vector
                autoGrpVector = pm.createNode('plusMinusAverage')
                autoGrpVector.operation.set(2)  # subtract
                autoGrpTrans_plug = VM_N.vectorProduct([0, 0, 0], None, 4, "%s.worldMatrix[0]" % str(vRefGrpTotal_list[i]), False)
                autoGrpTrans_plug.connect(autoGrpVector.input3D[0])
                noTwistGrpTrans_plug.connect(autoGrpVector.input3D[1])

                autoGrpTrans_plug.node().rename("skirt_autogrpTrans")
                noTwistGrpTrans_plug.node().rename("skirt_noTwistGrpTrans")

                # normalize grp vector #
                # we can get a vector with len 0, this will give us an error, so create a condition to avoid
                normalizeAutoGrpVec = pm.createNode('vectorProduct')
                normalizeAutoGrpVec.operation.set(0)
                normalizeAutoGrpVec.normalizeOutput.set(True)
                autoGrpVector.output3D.connect(normalizeAutoGrpVec.input1)

                # get iniDots
                iniDotY = VM_N.dotProduct(refVectorY, normalizeAutoGrpVec.output)
                iniDotZ = VM_N.dotProduct(refVectorZ, normalizeAutoGrpVec.output)
                # get dots
                dotXY = VM_N.dotProduct(refVectorY, maskDotVector)
                dotXZ = VM_N.dotProduct(refVectorZ, maskDotVector)

                # normalize values
                normVal = abs(iniDotY.get()[0]) + abs(iniDotZ.get()[0])  # abs values, to avoid errors
                normalizeNode = VM_N.multiplyDivive([None, iniDotY.children()[0], iniDotZ.children()[0]],
                                                    [normVal, normVal, normVal], 2)

                # multiplyDots Z and Y
                relDotY_node = VM_N.multDoubleLinear(dotXY.children()[0], normalizeNode.children()[1])

                # y
                relDotZ_node = VM_N.multDoubleLinear(dotXZ.children()[0], normalizeNode.children()[2])

                # plus z and y dot values
                dotCtrBlend = VM_N.plusMinusAverage(1, relDotY_node, relDotZ_node)

                # clamp dotCtrBlend
                dotClamp = DGU.clamp(dotCtrBlend).children()[0]

                ## blend orientations
                blendQuat = VM_N.quatSlerp(noTwistQuat, refNoOrientQuat, dotClamp, 0)
                blendQuat.node().rename("quatByskirt_sLerp")

                # decompose matrix
                if not lastNoTwistRef_grp:
                    VM_N.quatToEuler(blendQuat).connect(autoGrp.rotate)
                else:
                    # if another matrix exists yet, we should combine them
                    # det last decomposeMatrix and save it
                    blendQuatNode = autoGrpTotal_list[i].rotate.inputs()[0]  # quatToEuler
                    quatSLerp = blendQuatNode.inputQuat.inputs()[0]  # quatSlerp
                    #lastQuat = quatSLerp.input2Quat.inputs(p=True)[0]  # a decompose matrix quat
                    lastZeroQuat = quatSLerp.input1Quat.inputs(p=True)[0]  # a decompose matrix quat
                    blendQuatNode.inputQuat.disconnect()  # disconnect the last quat

                    # old connection
                    offsetQuat = VM_N.quatProd(quatSLerp.outputQuat, VM_N.quatInvert(lastZeroQuat))
                    o_OffsetAng = VM_N.quatToAxisAngle(offsetQuat)[0]

                    # new connection
                    offsetQuat = VM_N.quatProd(blendQuat, VM_N.quatInvert(refNoOrientQuat))
                    n_OffsetAng = VM_N.quatToAxisAngle(offsetQuat)[0]

                    # compare rotations
                    floatConditionSum = VM_N.plusMinusAverage(1, o_OffsetAng, n_OffsetAng)
                    floatCondnonZero = DGU.floatCondition(floatConditionSum, 0.0, 0, 0.01, floatConditionSum)  # avoid divide by 0
                    floatConditionNorm = VM_N.multiplyDivive(o_OffsetAng, floatCondnonZero, 2)

                    # wAddMatrix
                    wAddMatrix = VM_N.quatSlerp(quatSLerp.outputQuat, blendQuat, floatConditionNorm.children()[0])

                    # reconnect decompose matrix
                    wAddMatrix.connect(blendQuatNode.inputQuat)

            # store info of the last driver
            lastNoTwistRef_grp = noTwistRef_grp

        # conenct to joints
        for i, pointChanCtr in enumerate(pointControllers):
            for j, pointCtr in enumerate(pointChanCtr):
                pm.pointConstraint(pointCtr, skirtJointsArrange[i][j], maintainOffset=False)
                pm.orientConstraint(pointCtr, skirtJointsArrange[i][j], maintainOffset=False)
