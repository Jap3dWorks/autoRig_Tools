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
        spineJoints = [point for point in pm.ls() if re.match('^%s.*((hips)|(spine)|(chest)).*joint$' % self.chName, str(point))]
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

            # spine type controllers only translate, lock unused attr
            if 'spine' in ctrType:
                ARCore.lockAndHideAttr(spineController, False, True, True)

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

        # once created roots, we can freeze and hide attributes. if not, it can be unstable
        for neckHeadIKCtr in spineFKControllerList[1:]:
            ARCore.lockAndHideAttr(neckHeadIKCtr, True, False, False)

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
                spineIkCtrConstr.rename(str(joint).replace('joint', 'ctr'))  # rename ctr, useful for snap proxy model
                # constraint
                pm.pointConstraint(self.jointDriverList[n], joint, maintainOffset=False,  name='%s_drv_%s_%s_1_pointConstraint' % (self.chName, zone, jointNameSplit))
                endJointOrientConstraint = pm.orientConstraint(self.spineIKControllerList[min(n, len(self.spineIKControllerList)-1)], joint, maintainOffset=True, name='%s_drv_%s_%s_1_orientConstraint' % (self.chName, zone, jointNameSplit))
                endJointOrientConstraint.interpType.set(0)

            else:
                # connect to deform joints
                self.jointDriverList[n].rename(str(joint).replace('joint', 'main'))  # rename driver, useful for snap proxy model
                pm.parentConstraint(self.jointDriverList[n], joint, maintainOffset=True, name='%s_drv_%s_%s_1_parentConstraint' % (self.chName, zone, jointNameSplit))

        # stretch TODO: print spineJoints list
        ARCore.stretchCurveVolume(spineCurve, spineJoints, '%s_%s' % (self.chName, zone), self.mainCtr)

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
        neckHeadJoints = [point for point in pm.ls() if re.match('^%s.*(neck|head).*joint$' % self.chName, str(point))]
        logger.debug('Neck head joints: %s' % neckHeadJoints)
        positions = [point.getTranslation(space='world') for point in neckHeadJoints[:-1]]

        neckHeadCurveTransform = pm.curve(ep=positions, name='%s_%s_1_crv' % (self.chName, zone))
        # parent to noXform grp
        noXformNeckHeadGrp = pm.group(empty=True, name='%s_noXform_%s_grp' % (self.chName, zone))
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
            neckHeadDriver = pm.group(name='%s_curve_%s_%s_drv' % (self.chName, zone, n+1), empty=True)
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
                neckHeadIKCtr = self.create_controller('%s_%s_%s_1_ik_ctr' % (self.chName, zone, ctrType), '%sIk' % ctrType, 1, 17)
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
                    neckHeadFKCtr = self.create_controller('%s_%s_%s_1_fk_ctr' % (self.chName, zone, ctrType), 'neckFk1',1,4)
                    neckHeadFKCtr.setTranslation(neckHeadJoints[0].getTranslation('world'), 'world')
                    neckHeadFKCtrList.append(neckHeadFKCtr)

                    neckHeadFKCtr2 = self.create_controller('%s_%s_%s_2_fk_ctr' % (self.chName, zone, ctrType), 'neckFk', 1, 4)
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
        # once created roots, we can freeze and hide attributes. if not, it can be unstable
        for neckHeadFKCtr in neckHeadFKCtrList:
            ARCore.lockAndHideAttr(neckHeadFKCtr, True, False, False)
        # lock and hide neck attr, it's here because we have only one
        ARCore.lockAndHideAttr(self.neckHeadIKCtrList[0], False, True, True)

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
            # TODO: rename all this
            if re.match('.*tip.*', str(joint)):
                continue

            jointNameSplit = str(joint).split('_')[1]
            # review: create parent constraints, once drivers have been created, if not, all flip
            if re.match('.*head.*', str(joint)):
                # head joint, with point to driver, and orient to controller
                pm.pointConstraint(self.neckHeadJointDriverList[n], joint, maintainOffset=False, name='%s_drv_%s_%s_1_pointConstraint' % (self.chName, zone, jointNameSplit))
                # orient to controller
                self.neckHeadIKCtrList[-1].rename(str(joint).replace('joint', 'ctr'))  # rename, useful for snap proxy model
                pm.orientConstraint(self.neckHeadIKCtrList[-1], joint, maintainOffset=True, name='%s_drv_%s_%s_1_orientConstraint' % (self.chName, zone, jointNameSplit))

            else:
                self.neckHeadJointDriverList[n].rename(str(joint).replace('joint', 'main'))  # rename, useful for snap proxy model
                pm.parentConstraint(self.neckHeadJointDriverList[n], joint, maintainOffset=True, name='%s_drv_%s_%s_1_parentConstraint' % (self.chName, zone, jointNameSplit))

        # stretch
        ARCore.stretchCurveVolume(neckHeadCurve, neckHeadJoints[:-1], '%s_%s' % (self.chName, zone), self.mainCtr)

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
        ikFkJoints = [point for point in pm.ls() if re.match('^%s.*(%s).(?!twist).*%s.*joint$' % (self.chName, zoneA, side), str(point).lower())]
        self.ikFkTwistJoints = [point for point in pm.ls() if re.match('^%s.*(%s).(twist).*%s.*joint$' % (self.chName, zoneA, side), str(point).lower())]
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
        for n, i in enumerate(ikFkJoints):
            controllerName = str(i).split('_')[1] if 'end' not in str(i) else 'end'  # if is an end joint, rename end
            self.ikFk_FkControllersList.append(i.duplicate(po=True, name='%s_%s_%s_%s_fk_ctr' % (self.chName, zoneA, side, controllerName))[0])
            self.ikFk_IkJointList.append(i.duplicate(po=True, name='%s_%s_%s_%s_ik_joint' % (self.chName, zoneA, side, controllerName))[0])
            self.ikFk_MainJointList.append(i.duplicate(po=True, name='%s_%s_%s_%s_main_joint' % (self.chName, zoneA, side, controllerName))[0])

            ### twist Joints ####
            if ikFkTwistSyncJoints[n]:
                ikFkTwistIni = [i.duplicate(po=True, name='%s_twist0_%s_%s_%s_joint' % (self.chName, zoneA, side, controllerName))[0]]

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

                # create twist group orient tracker, if is chaint before foot or hand, track foot or hand
                if ikFkTwistSyncJoints[n] == ikFkTwistSyncJoints[-2]:  # just before end joint
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
        for i, fkCtr in enumerate(self.ikFk_FkControllersList[:-1]):  # last controller does not has shape
            # ik hierarchy
            self.ikFk_IkJointList[i].addChild(self.ikFk_IkJointList[i + 1])
            # main hierarchy
            self.ikFk_MainJointList[i].addChild(self.ikFk_MainJointList[i + 1])

            fkCtr.addChild(self.ikFk_FkControllersList[i + 1])
            # fk controls
            shapeFkTransform = self.create_controller('%sShape' % str(fkCtr), '%sFk_%s' % (NameIdList[i], side), 1, fkColor)
            # parentShape
            fkCtr.addChild(shapeFkTransform.getShape(), s=True, r=True)
            # delete shape transform
            pm.delete(shapeFkTransform)

        # ik control
        self.ikFk_IkControl = self.create_controller('%s_ik_%s_%s_ctr' % (self.chName, zoneA, side), '%sIk_%s' % (zoneA, side), 1, 17)
        self.ikFk_IkControl.setTranslation(ikFkJoints[-1].getTranslation('world'), 'world')
        self.ikFkCtrGrp.addChild(self.ikFk_IkControl)  # parent to ctr group

        # organitze outliner
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
        ikFkPoleController = self.create_controller('%s_ik_%s_%s_pole_ctr' % (self.chName, zoneA, side), 'pole',2)
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
            ikFk_FkrootsDistances, ikFk_MaxiumDistance = ARCore.calcDistances(self.ikFk_FkCtrRoots)  # review:  legIkJointList[0]   legIkCtrRoot
            #ikFkStretchSetup
            ARCore.stretchIkFkSetup(self.ikFk_FkCtrRoots[1:], ikFk_FkrootsDistances, self.ikFkshape, [self.ikFk_IkJointList[0], ikHandle],
                                    ikFk_MaxiumDistance, self.ikFk_IkJointList[1:], self.ikFk_MainJointList[1:], ikFkTwistList, '%s_%s_%s' % (self.chName, zoneA, side), self.mainCtr, ikFkPoleController)

        # iterate along main joints
        # blending
        # todo: visibility, connect to ikFkShape
        for i, joint in enumerate(self.ikFk_MainJointList):
            # attributes
            orientConstraint = pm.orientConstraint(self.ikFk_IkJointList[i], self.ikFk_FkControllersList[i], joint, maintainOffset=False, name='%s_main_blending_%s_%s_orientConstraint' % (self.chName, zoneA, side))
            self.ikFkshape.ikFk.connect(orientConstraint.attr('%sW0' % str(self.ikFk_IkJointList[i])))
            self.ikFkshape.ikFk.connect(self.ikFk_IkJointList[i].visibility)

            # parent shape
            self.ikFk_FkControllersList[i].addChild(self.ikFkshape, s=True, add=True)

            self.plusMinusIkFk.output1D.connect(orientConstraint.attr('%sW1' % str(self.ikFk_FkControllersList[i])))
            # review: visibility shape
            self.plusMinusIkFk.output1D.connect(self.ikFk_FkControllersList[i].visibility)

            ARCore.lockAndHideAttr(self.ikFk_FkControllersList[i], True, False, False)
            pm.setAttr('%s.radi' % self.ikFk_FkControllersList[i], channelBox=False, keyable=False)

        # twist joints bending bones connect, if curve wire detected, no use bendingJoints
        # TODO: control by twist or wire?
        if ikFkTwistList:
            # if twist joints, we could desire bending controls or not
            if bendingBones:
                ARCore.twistJointBendingBoneConnect(parent, self.ikFk_MainJointList, ikFkTwistList, ikFkJoints, ikFkTwistSyncJoints, self.chName, zone, side, NameIdList, self.path)
            else:
                ARCore.twistJointConnect(self.ikFk_MainJointList, ikFkTwistList, ikFkJoints, ikFkTwistSyncJoints)

        # or connect the rig with not twist joints
        else:
            for i, joint in enumerate(self.ikFk_MainJointList):
                # connect to deform skeleton
                joint.rename(str(ikFkJoints[i]).replace('joint', 'main'))  # rename, useful for snap proxy model
                pm.orientConstraint(joint, ikFkJoints[i], maintainOffset=False, name='%s_main_%s_%s_parentConstraint' % (self.chName, zoneA, side))
                pm.pointConstraint(joint, ikFkJoints[i], maintainOffset=False, name='%s_main_%s_%s_parentConstraint' % (self.chName, zoneA, side))

        # ik blending controller attr
        self.ikFkshape.ikFk.connect(ikFkPoleController.visibility)
        self.ikFkshape.ikFk.connect(self.ikFk_IkControl.visibility)
        self.ikFk_IkControl.addChild(self.ikFkshape, add=True, s=True)

        # function for create foots, Review: maybe here another to create hands
        for func in funcs:
            ikControllers, fkControllers = func()
            self.ikFk_IkControllerList = self.ikFk_IkControllerList + ikControllers
            self.ikFk_FkControllersList = self.ikFk_FkControllersList + fkControllers

        # save Data
        # todo: save quaternions too if necessary
        zoneSide = '%s_%s' % (zoneA, side)
        self.joints[zoneSide] = ikFkJoints
        self.ikControllers[zoneSide] = self.ikFk_IkControllerList
        self.fkControllers[zoneSide] = self.ikFk_FkControllersList
        self.ikHandles[zoneSide] = ikHandle

        # delete ikfkShape
        pm.delete(ikFkNode)

        return self.ikFk_IkControllerList, self.ikFk_FkControllersList


    def foot_auto(self, zones=('leg','foot', 'toe'), planeAlign=None, *funcs):
        """
        # TODO: organize and optimize this Func
        # TODO: get zoneA from last ikFk executed func
        This method should be called as a *arg for ikFkChain_auto.
        auto build a ik fk foot
        Args:
            side: left or right
            zone: foot
        """
        zoneA = zones[0]
        zoneB = zones[1]
        zoneC = zones[2]
        fkColor = 14 if self.lastSide =='left' else 29
        toesJoints = [point for point in pm.ls() if re.match('^%s.*(%s).(?!_end)(?!0)(?!twist).*%s.*joint$' % (self.chName, zoneC, self.lastSide), str(point))]
        toesZeroJoints = [point for point in pm.ls() if re.match('^%s.*(%s).(?!_end)(?=0)(?!twist).*%s.*joint$' % (self.chName, zoneC, self.lastSide), str(point))]
        footJoints = [point for point in pm.ls() if re.match('^%s.*(%s).*((?!twist).).*%s.*joint$' % (self.chName, zoneB, self.lastSide), str(point))]

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
            controllerName = str(joint).split('_')[1]
            logger.debug('foot controller name: %s' % controllerName)
            footFkCtr = joint.duplicate(po=True, name='%s_%s_%s_%s_fk_ctr' % (self.chName, zoneB, self.lastSide, controllerName))[0]
            footMain = joint.duplicate(po=True, name='%s_%s_%s_%s_main_joint' % (self.chName, zoneB, self.lastSide, controllerName))[0]

            # get transformMatrix and orient new controller TODO: function
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

        # parent fk controller under leg
        self.ikFk_FkControllersList[-1].addChild(footFkControllerList[0])
        self.ikFk_MainJointList[-1].addChild(footMainJointsList[0])

        # twistJointsConnections
        if self.ikFkTwistJoints:
            ARCore.twistJointsConnect(self.footTwstList, footMainJointsList[0], '%s_%s_%s_%s' % (self.chName, self.footTwstCtrName, self.footTwstZone, self.lastSide), self.footpointCnstr)

        # TODO: function from joint, ik, fk, main?
        # create toe Fk and ik ctr
        # last foot fkCtr, easiest fot later access
        toeIkCtrParents = []  # list with first joint of toes chains
        toeMainParents = []
        for i, toe in enumerate(toesJointsArr):
            toeFkChain = []
            toeIkChain = []
            toeMainChain = []
            for joint in toe:
                controllerName = str(joint).split('_')[1]
                logger.debug('foot controller name: %s' % controllerName)
                toeFkCtr = joint.duplicate(po=True, name='%s_%s_%s_%s_fk_ctr' % (self.chName, zoneB, self.lastSide, controllerName))[0]
                toeMainJnt = joint.duplicate(po=True, name='%s_%s_%s_%s_main_joint' % (self.chName, zoneB, self.lastSide, controllerName))[0]
                toeIkCtr = joint.duplicate(po=True, name='%s_%s_%s_%s_ik_ctr' % (self.chName, zoneB, self.lastSide, controllerName))[0]

                # get transformMatrix and orient new controller # TODO: function
                matrix = pm.xform(toeFkCtr, ws=True, q=True, m=True)
                matrix = ARCore.orientToPlane(matrix, planeAlign)  # adjusting orient to plane zx

                # apply transforms constrollers
                pm.xform(toeFkCtr, ws=True, m=matrix)
                pm.xform(toeIkCtr, ws=True, m=matrix)

                # fk ik toe control Shape
                shape = self.create_controller('%sShape' % str(toeFkCtr), '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
                toeFkCtr.addChild(shape.getShape(), s=True, r=True)
                pm.delete(shape)
                shape = self.create_controller('%sShape' % str(toeIkCtr), '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
                toeIkCtr.addChild(shape.getShape(), s=True, r=True)
                pm.delete(shape)

                # if joint Chain, reconstruct hierarchy
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

            # middle toe, useful later to general toe controller  # review
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
        # TODO: create the rest of the controllers here too
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
        toeFkGeneralController = self.create_controller('%s_fk_%s_%s_toeGeneral_ctr' % (self.chName, zoneB, self.lastSide), 'toesFk', 1, fkColor)
        pm.xform(toeFkGeneralController, ws=True, m=middleToeCtrMatrix)  # align to middle individual toe review
        toeIkGeneralController = self.create_controller('%s_ik_%s_%s_toeGeneral_ctr' % (self.chName, zoneB, self.lastSide), 'toesFk', 1, fkColor)
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

        # lock and hide attributes. after root creation
        ARCore.lockAndHideAttr(footIkControllerList[1:], True, False, True)
        ARCore.lockAndHideAttr(toesIkControllerList[-1], True, False, True)

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

            ARCore.lockAndHideAttr(footFkControllerList[i], True, False, False)
            pm.setAttr('%s.radi' % footFkControllerList[i], channelBox=False, keyable=False)

            # connect to deform skeleton
            mainJoint.rename(str(footJoints[i]).replace('joint', 'main'))  # rename, useful for snap proxy model
            pm.orientConstraint(mainJoint, footJoints[i], maintainOffset=False, name='%s_%s_%s_%s_joint_orientConstraint' % (self.chName, controllerName, zoneB, self.lastSide))

        ## TOES ##
        # main ik fk toes
        for i, mainJoint in enumerate(toesMainJointsList):
            controllerName = toeControllerNameList[i]
            orientConstraint = pm.orientConstraint(toesIkControllerList[i], toesFkControllerList[i], mainJoint, maintainOffset=True, name='%s_%s_%s_%s_mainBlending_orientConstraint' % (self.chName, controllerName, zoneB, self.lastSide))

            self.ikFkshape.ikFk.connect(orientConstraint.attr('%sW0' % str(toesIkControllerList[i])))  # shape with bleeding attribute
            self.ikFkshape.ikFk.connect(toesIkControllerList[i].visibility)  # all foot chain visibility

            self.plusMinusIkFk.output1D.connect(orientConstraint.attr('%sW1' % str(toesFkControllerList[i])))
            self.plusMinusIkFk.output1D.connect(toesFkControllerList[i].visibility)

            pm.setAttr('%s.radi' % toesFkControllerList[i], channelBox=False, keyable=False)

            # connect to deform skeleton, review: point constraint toes main. strange behaviour
            mainJoint.rename(str(toesJoints[i]).replace('joint', 'main'))  # rename, useful for snap proxy model
            pm.orientConstraint(mainJoint, toesJoints[i], maintainOffset=False, name='%s_%s_%s_%s_joint_orientConstraint' % (self.chName, controllerName, zoneA, self.lastSide))
            pm.pointConstraint(mainJoint, toesJoints[i], maintainOffset=False, name='%s_%s_%s_%s_joint_pointConstraint' % (self.chName, controllerName, zoneA, self.lastSide))


        return footIkControllerList + toesIkControllerList, footFkControllerList + toesFkControllerList

    def hand_auto(self, zones=('arm', 'hand', 'finger'), planeAlign=None, *funcs):
        """
        This method should be called as a *arg for ikFkChain_auto.
        auto build hand
        Args:
            side:
            zones:
            *funcs:
        Returns:
        """
        # zoneA = zones[0]
        zoneB = zones[1]
        zoneC = zones[2]
        fkColor = 14 if self.lastSide == 'left' else 29  # review, more procedural
        fingerJoints = [point for point in pm.ls() if re.match('^%s.*(%s).(?!_end)(?!0)(?!twist).*%s.*joint$' % (self.chName, zoneC, self.lastSide), str(point))]
        fingerZeroJoints = [point for point in pm.ls() if  re.match('^%s.*(%s).(?!_end)(?=0)(?!twist).*%s.*joint$' % (self.chName, zoneC, self.lastSide), str(point))]
        handJoints = [point for point in pm.ls() if re.match('^%s.*(%s).*((?!twist).).*%s.*joint$' % (self.chName, zoneB, self.lastSide), str(point))]

        # arrange toes by joint chain p.e [[toea, toesa_Tip], [toeb, toeb_tip]]
        fingerJointsArr = ARCore.arrangeListByHierarchy(fingerJoints)

        # controllers and main lists
        handFkControllerList = []  # fk lists
        handIkControllerList = []  # ik lists
        handMainJointsList = []  # main lists
        fingerMainJointsList = []

        handControllerNameList = []
        fingerControllerNameList = []
        # create foot ctr
        for joint in handJoints:
            controllerName = str(joint).split('_')[1]
            logger.debug('foot controller name: %s' % controllerName)
            footFkCtr = joint.duplicate(po=True, name='%s_%s_%s_%s_fk_ctr' % (self.chName, zoneB, self.lastSide, controllerName))[0]
            footMain = joint.duplicate(po=True, name='%s_%s_%s_%s_main_joint' % (self.chName, zoneB, self.lastSide, controllerName))[0]

            # get transformMatrix and orient new controller TODO: function
            matrix = pm.xform(footFkCtr, ws=True, q=True, m=True)

            matrix = ARCore.orientToPlane(matrix, planeAlign)  # adjusting orient to plane zx
            pm.xform(footFkCtr, ws=True, m=matrix)  # new transform matrix with vector adjust

            # fk control Shape
            shape = self.create_controller('%sShape' % str(footFkCtr), '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
            footFkCtr.addChild(shape.getShape(), s=True, r=True)
            pm.delete(shape)

            if not handFkControllerList:
                # save this matrix, to apply latter if necessary
                firstfootFkMatrix = matrix

            else:  # if more than 1 joint, reconstruct hierarchy
                handFkControllerList[-1].addChild(footFkCtr)
                handMainJointsList[-1].addChild(footMain)

            # save controllers
            handControllerNameList.append(controllerName)
            handFkControllerList.append(footFkCtr)
            handMainJointsList.append(footMain)

        # parent fk controller under leg
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
                controllerName = str(joint).split('_')[1]
                logger.debug('foot controller name: %s' % controllerName)
                fingerMainJnt = joint.duplicate(po=True, name='%s_%s_%s_%s_main_joint' % (self.chName, zoneB, self.lastSide, controllerName))[0]

                # main finger control Shape
                shape = self.create_controller('%sShape' % str(fingerMainJnt), '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
                fingerMainJnt.addChild(shape.getShape(), s=True, r=True)
                pm.delete(shape)

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
                                                       name='%s_%s_%s_%s_mainBlending_orientConstraint' % (self.chName, controllerName, zoneB, self.lastSide))
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
                                                       name='%s_%s_%s_%s_mainBlending_orientConstraint' % (self.chName, controllerName, zoneB, self.lastSide))

            ARCore.lockAndHideAttr(handFkControllerList[i], True, False, False)
            pm.setAttr('%s.radi' % handFkControllerList[i], channelBox=False, keyable=False)

            # connect to deform skeleton
            mainJoint.rename(str(handJoints[i]).replace('joint', 'main'))  # rename, useful for snap proxy model
            pm.orientConstraint(mainJoint, handJoints[i], maintainOffset=False, name='%s_%s_%s_%s_joint_orientConstraint' % (self.chName, controllerName, zoneB, self.lastSide))

            ## finger ##
            # main ik fk toes
            for i, mainJoint in enumerate(fingerMainJointsList):
                controllerName = fingerControllerNameList[i]
                pm.setAttr('%s.radi' % mainJoint, channelBox=False, keyable=False)

                # connect to deform skeleton, review: point constraint toes main. strange behaviour
                mainJoint.rename(str(fingerJoints[i]).replace('joint', 'ctr'))
                pm.orientConstraint(mainJoint, fingerJoints[i], maintainOffset=False,  name='%s_%s_%s_%s_joint_orientConstraint' % (self.chName, controllerName, zoneC, self.lastSide))
                pm.pointConstraint(mainJoint, fingerJoints[i], maintainOffset=False,  name='%s_%s_%s_%s_joint_pointConstraint' % (self.chName, controllerName, zoneC, self.lastSide))

                if '1' in controllerName:
                    for zeroJoint in fingerZeroJoints:
                        if controllerName[:-1] in str(zeroJoint):
                            # create null grp to snap roxy model
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
        clavicleJoints = [point for point in pm.ls() if re.match('^%s.*(%s).(?!_end)(?!0)(?!twist).*%s.*joint$' % (self.chName, zone, self.lastSide), str(point))]
        clUpperArmJoint = clavicleJoints[-1].getChildren()[0]

        parent = self.ikFk_MainJointList[0].firstParent()  # get parent of the system

        parentChilds = [child for child in parent.listRelatives(c=True, type='transform') if (self.lastSide in str(child)) and (self.lastZone in str(child).lower()) and not ('pole' in str(child))]

        logger.debug('childs: %s' %parentChilds)

        # store clavicle main joints here
        clavicleMainList = []

        for joint in clavicleJoints:
            controllerName = str(joint).split('_')[1]
            # create controller shape
            clavicleController = self.create_controller(str(joint).replace('joint', 'main'), '%sFk_%s' % (controllerName, self.lastSide), 1, fkColor)
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
        ARCore.createRoots([clavicleSwingCrt])

        # auto clavicle
        autoClavicleName = 'autoClavicleInfluence'
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
            clavicleMainList[i].rename(str(joint).replace('joint','ctr'))
            pm.pointConstraint(clavicleMainList[i], joint, maintainOffset=False)
            pm.orientConstraint(clavicleMainList[i], joint, maintainOffset=True)

        return [], clavicleMainList

    def addCluster(self, cluster, parent, controllerType):
        """
        Take a cluster or create it, move it to the controller system, create a controller and vinculate
        :arg: cluster(str or pm): name of the cluster transform node
        :return:
        """
        # cluster var type
        if isinstance(cluster, str):
            cluster = pm.PyNode(cluster)
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
        controller = self.create_controller('%s_ctr' % str(cluster), controllerType, 1.0, 24)
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


    def create_controller(self, name, controllerType, s=1.0, colorIndex=4):
        """
        Args:
            name: name of controller
            controllerType(str): from json controller types
        return:
            controller: pymel transformNode
            transformMatrix: stored position
        """
        controller, transformMatrix = ctrSaveLoadToJson.ctrLoadJson(controllerType, self.chName, self.path, s, colorIndex)
        controller = pm.PyNode(controller)
        controller.rename(name)

        shapes = controller.listRelatives(s=True)
        # hide shape attr
        for shape in shapes:
            for attr in ('aiRenderCurve', 'aiCurveWidth', 'aiSampleRate', 'aiCurveShaderR', 'aiCurveShaderG', 'aiCurveShaderB'):
                pm.setAttr('%s.%s' % (str(shape), attr), channelBox=False, keyable=False)

        pm.xform(controller, ws=True, m=transformMatrix)
        logger.debug('controller %s' % controller)
        return controller