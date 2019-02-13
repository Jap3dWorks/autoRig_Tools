from pymel import core as pm

from ARCore import DGUtils, createController, jointPointToController


def stretchIkFkSetup(fkObjList, fkDistances, nodeAttr, ikObjList, ikDistance, ikJoints, mainJoints, twsitMainJoints, nameInfo, main, poleVector=None):
    """
    create ik and fk stretch system with twistJoints, stretching by translate
    some lists must be of the same len()
    TODO: restructure this, maybe should restructure autoRig ikFk -> ikFk Class?
    Args:
        fkObjList : roots fk controllers that will stretch (no the first root)
        fkDistances(list(float)): list of distances between chain elements 2 --
        nodeAttr(pm.dagNode): shape with ikFk attribute, where fk stretch attribute will be added
        ikObjList(list): top object and lower object in a ik system 2 --
        ikDistance(float): maximum distance between top and lower element in a ik and fk system # calculate in the func?
        ikJoints(list): ikJoints that will stretch (no the first joint) 2 --
        char, zone, side: info
        mainJoints(list(pm.Joint)): MainJoints to connect the stretch (no the first joint) 2 --
        twsitMainJoints(list(list(pm.joints))) : lists with twist joints
        char, zone, side(str): name of character. zone os the system. side of the system
        main(PyNode): main controller
    TODO: less nodes, new node when all connections are used
    """
    # fk system
    # create attr
    attrName = 'fkStretch'
    pm.addAttr(nodeAttr, longName=attrName, shortName=attrName, minValue=.2, maxValue=5, type='float', defaultValue=1.0, k=True)
    outputFk = []
    fkOutRangeParent = fkObjList[-1].listRelatives(ad=True, type='transform')[0]  # store last fk or group created
    for n, mainJnt in enumerate(mainJoints):
        # stretch operations
        multiplyFk = pm.createNode('multiplyDivide', name='%s_fkStretch_multiplyDivide' % nameInfo)
        multiplyFk.input1X.set(fkDistances[n])
        nodeAttr.attr(attrName).connect(multiplyFk.input2X)

        if n < len(fkObjList):
            multiplyFk.outputX.connect(fkObjList[n].translateX)

        else:
            # fk object do not exists, so we create a empty grp
            fkStretchGrp = pm.group(empty=True, name='%s_fkStretch%s_grp' % (nameInfo, n - len(fkObjList)-1))
            pm.xform(fkStretchGrp, ws=True, m=pm.xform(mainJnt, ws=True, q=True, m=True))  # align group
            fkOutRangeParent.addChild(fkStretchGrp)  # reconstruct hierarchy
            multiplyFk.outputX.connect(fkStretchGrp.translateX)  # connect x translate value
            # set again last object
            fkOutRangeParent = fkStretchGrp

        outputFk.append(multiplyFk)

    # conserveVolume using conditionalScaleFactor ->  1/conditionalScaleFactor   get inverse
    fkConserveVolumeScaleFactor = pm.createNode('multiplyDivide', name='%s_fkConserveVolume_multiplyDivide' % nameInfo)
    fkConserveVolumeScaleFactor.operation.set(2)  # set to divide
    fkConserveVolumeScaleFactor.input1X.set(1)
    nodeAttr.attr(attrName).connect(fkConserveVolumeScaleFactor.input2X)

    # need invert
    # invert  # todo: maybe this in conserveVolumeAnimNode func
    fkCVScaleFactorInvert = pm.createNode('plusMinusAverage', name='%s_fkStretch_Invert_plusMinusAverage' % nameInfo)
    fkCVScaleFactorInvert.operation.set(2)  # substract
    fkCVScaleFactorInvert.input1D[0].set(1)
    fkConserveVolumeScaleFactor.outputX.connect(fkCVScaleFactorInvert.input1D[1])

    ## ik system ##
    if poleVector:  # if pole, create snap to pole
        snapPoleAttrStr = 'snapToPole'
        snapPoleAttr = pm.addAttr(nodeAttr, longName=snapPoleAttrStr, shortName=snapPoleAttrStr, minValue=0, maxValue=1, type='float', defaultValue=0.0, k=True)

    distanceBetweenPoleList=[]
    # distance between objetcs, and connect matrix
    distanceBetween = pm.createNode('distanceBetween', name='%s_ikStretch_distanceBetween' % nameInfo)
    scaleDistance = pm.createNode('multiplyDivide', name='%s_ikStretchScale_multiplyDivide' % nameInfo)
    scaleDistance.operation.set(2)  # divide
    distanceBetween.distance.connect(scaleDistance.input1X)
    main.scaleX.connect(scaleDistance.input2X)

    for i in range(len(ikObjList)):
        # use helpers to avoid cycle checks
        positionTrackIk = pm.group(empty=True, name='%s_ikStretch_track%s__grp' % (nameInfo, i+1))
        ikObjList[i].firstParent().addChild(positionTrackIk)
        pm.xform(positionTrackIk, ws=True, m=pm.xform(ikObjList[i], ws=True, q=True, m=True))

        positionTrackIk.worldMatrix[0].connect(distanceBetween.attr('inMatrix%s' % (i+1)))

        # for knee snap, extract distances from each point to pole vector
        if poleVector:
            distanceBetweenPole = pm.createNode('distanceBetween', name='%s_ikStretch_distancePole%s_distanceBetween' % (nameInfo, i+1))
            distancePoleScale = pm.createNode('multiplyDivide', name='%s_ikStretch_distanceScalePole%s_multiplyDivide' % (nameInfo, i+1))
            distancePoleScale.operation.set(2)  # divide
            positionTrackIk.worldMatrix[0].connect(distanceBetweenPole.inMatrix1)
            poleVector.worldMatrix[0].connect(distanceBetweenPole.inMatrix2)
            distanceBetweenPole.distance.connect(distancePoleScale.input1X)
            main.scaleX.connect(distancePoleScale.input2X)
            if ikJoints[i].translateX.get() < 0:
                invertValue = pm.createNode('multiplyDivide', name='%s_ikStretch_invertValue_multiplyDivide' % nameInfo)
                invertValue.input2X.set(-1)
                distancePoleScale.outputX.connect(invertValue.input1X)

                distancePoleScale = invertValue

            distanceBetweenPoleList.append(distancePoleScale)

    # conditional node
    conditionalScaleFactor = pm.createNode('condition', name='%s_ikStretch_stretchValue_condition' % nameInfo)  # TIP stretchValue here
    conditionalScaleFactor.operation.set(2)
    conditionalScaleFactor.colorIfFalseR.set(1)
    # connect distance to conditional
    scaleDistance.outputX.connect(conditionalScaleFactor.firstTerm)
    conditionalScaleFactor.secondTerm.set(abs(ikDistance))
    # scaleFactor
    multiplydivide = pm.createNode('multiplyDivide', name='%s_ikStretch_multiplyDivide' % nameInfo)
    multiplydivide.operation.set(2)  # set to divide
    scaleDistance.outputX.connect(multiplydivide.input1X)
    multiplydivide.input2X.set(abs(ikDistance))
    # connecto to conditional
    multiplydivide.outputX.connect(conditionalScaleFactor.colorIfTrueR)
    # multiply scale factor by joints x transform
    # TODO: create node every 3 connections
    outputIk = []
    conserveVolumeJointList = []
    for i, joint in enumerate(ikJoints):
        multiplyTranslate = pm.createNode('multiplyDivide', name='%s_ikStretch_jointValue_multiplyDivide' % nameInfo)
        conditionalScaleFactor.outColorR.connect(multiplyTranslate.input1X)
        multiplyTranslate.input2X.set(joint.translateX.get())

        # connect to joint
        # with pole Vector snap
        if poleVector:
            ikStretchOutput = attrBlending(distanceBetweenPoleList[i], multiplyTranslate, nodeAttr.attr(snapPoleAttrStr), nameInfo, joint.translateX)

            multiplyTranslate = ikStretchOutput
        else:
            multiplyTranslate.outputX.connect(joint.translateX)

        # save per joint output
        outputIk.append(multiplyTranslate)

        # create a list with all twist joints of the system
        if twsitMainJoints:
            conserveVolumeJointList += twsitMainJoints[i]

    # conserveVolume using conditionalScaleFactor ->  1/conditionalScaleFactor   get inverse
    ikConserveVolumeScaleFactor = pm.createNode('multiplyDivide', name='%s_conserveVolume_multiplyDivide' % nameInfo)
    ikConserveVolumeScaleFactor.operation.set(2)  # set to divide
    ikConserveVolumeScaleFactor.input1X.set(1)
    conditionalScaleFactor.outColorR.connect(ikConserveVolumeScaleFactor.input2X)
    # create animNode to control scale
    conserveVolumeAnimCurve = pm.createNode('animCurveTU', name='%s_conserveVolume_animCurveTU' % nameInfo)
    # draw curve
    conserveVolumeAnimCurve.addKeyframe(0, 0.3)
    conserveVolumeAnimCurve.addKeyframe((len(conserveVolumeJointList) - 1) // 2, 1.0)
    conserveVolumeAnimCurve.addKeyframe(len(conserveVolumeJointList) - 2, 0.3)
    # invert cv  -> (1-cv)
    iKInvConserveVolumeF = pm.createNode('plusMinusAverage', name='%s_conserveVolume_invertFactor_animCurveTU' % nameInfo)
    iKInvConserveVolumeF.operation.set(2)  # substract
    iKInvConserveVolumeF.input1D[0].set(1)
    ikConserveVolumeScaleFactor.outputX.connect(iKInvConserveVolumeF.input1D[1])

    for i, CVJoint in enumerate(conserveVolumeJointList):
        # ik
        ikCVNode = conserveVolumeAnimNode(conserveVolumeAnimCurve, i, iKInvConserveVolumeF, ikConserveVolumeScaleFactor, nameInfo)
        # fk
        fkCVNode = conserveVolumeAnimNode(conserveVolumeAnimCurve, i, fkCVScaleFactorInvert, fkConserveVolumeScaleFactor, nameInfo)
        # main blending
        # connect to joint
        attrBlending(ikCVNode, fkCVNode, nodeAttr.attr('ikFk'), '%s_conserveVolume' % nameInfo, CVJoint.scaleY, CVJoint.scaleZ)

    # to main joints formula: A+(B-A)*blend for joint, add twistBones, and stretch too
    for i, fkOut in enumerate(outputFk):
        # blending
        plusMinusToMain = attrBlending(outputIk[i], fkOut, nodeAttr.attr('ikFk'), '%s_stretch' % nameInfo, mainJoints[i].translateX)
        # stretch to twist joints

        if twsitMainJoints:
            # twist joints main translate review names
            multiplyDivideTwstJnt = pm.createNode('multiplyDivide', name='%s_mainTwistStretch_multiplyDivide' % nameInfo)
            multiplyDivideTwstJnt.operation.set(2)  # divide
            multiplyDivideTwstJnt.input2X.set(len(twsitMainJoints[i])-1)  # try change sign here review
            plusMinusToMain.output1D.connect(multiplyDivideTwstJnt.input1X)
            # connect to joints
            for twstJnt in twsitMainJoints[i][1:]:
                # first joint of the twistMainJoint does not has to move ()
                multiplyDivideTwstJnt.outputX.connect(twstJnt.translateX)


def conserveVolumeAnimNode(animCurve, varyTime, invFactor, Factor, nameInfo):
    """
    create circuity nodes to attach a curveAnim to control outputs values. useful for better results on stretch
    Args:
        animCurve(animNode): anim curve
        varyTime(index): frame to track value from the curve
        invFactor(node): plusMinusAverage node with 1-Factor
        Factor(node): scale Factor maxium
        nameInfo: list of three elements with name info p.e('akona', 'leg', 'lowerLeg') # review

    Returns: multiplyDivide node with final factor

    """

    outputType = 'outputX' if isinstance(Factor, pm.nodetypes.MultiplyDivide) else 'output1D'

    # frame cache
    CVFrameCache = pm.createNode('frameCache', name='%s_%s_%s_conserveVolume_frame' % (nameInfo[0], nameInfo[1], nameInfo[2]))
    animCurve.output.connect(CVFrameCache.stream)
    CVFrameCache.varyTime.set(varyTime)  # i
    # multiply frame cache
    multiplyFrameCache = pm.createNode('multiplyDivide', name='%s_%s_%s_conserveVolume_multiplyDivide' % (nameInfo[0], nameInfo[1], nameInfo[2]))
    CVFrameCache.varying.connect(multiplyFrameCache.input1X)
    invFactor.output1D.connect(multiplyFrameCache.input2X)
    # plus conserveVolume
    plusConVolum = pm.createNode('plusMinusAverage', name='%s_%s_%s_conserveVolume_plusMinusAverage' % (nameInfo[0], nameInfo[1], nameInfo[2]))
    multiplyFrameCache.outputX.connect(plusConVolum.input1D[0])
    Factor.attr(outputType).connect(plusConVolum.input1D[1])
    # divide volumeScalefactor / plusConserveVolum
    divideConVol = pm.createNode('multiplyDivide', name='%s_%s_%s_conserveVolume_divide_multiplyDivide' % (nameInfo[0], nameInfo[1], nameInfo[2]))
    divideConVol.operation.set(2)  # division
    Factor.attr(outputType).connect(divideConVol.input1X)
    plusConVolum.output1D.connect(divideConVol.input2X)

    return divideConVol


def twistJointsConnect(twistMainJoints, trackMain, nameInfo, pointCnstr=None):
    """
    Connect and setup orient for twist joints
    Args:
        twistMainJoints(list)(pm.Joint): chain of twist joints
        trackMain(pm.Joint): main joint where trackGroup will be oriented constraint
        pointCnstr: object where the twistMainJoints[0] will be pointConstrained, if this arg is given, an extra group is created. to track correctly
        the main joint
        nameInfo: characterName_zone_side
    return:
    """
    # if not pointCnstr use main joint
    if pointCnstr:
        twistRefGrp = pm.group(empty=True, name='%s_twistOri_grp' % nameInfo)
        pm.xform(twistRefGrp, ws=True, ro=pm.xform(twistMainJoints[0], ws=True, q=True, ro=True))
        pm.xform(twistRefGrp, ws=True, t=pm.xform(trackMain, ws=True, q=True, t=True))
        trackMain.addChild(twistRefGrp)

    else:
        pointCnstr = trackMain
        twistRefGrp = trackMain

    # group that will be used for store orientation, with a orientConstraint
    trackGroup = pm.group(empty=True, name='%s_twistOri_grp' % nameInfo)

    pm.xform(trackGroup, ws=True, m=pm.xform(twistMainJoints[0], ws=True, q=True, m=True))
    twistMainJoints[0].addChild(trackGroup)  # parent first joint of the chain

    # constraint to main
    twstOrientCntr = pm.orientConstraint(twistRefGrp,twistMainJoints[0], trackGroup, maintainOffset=True, name='%s_twistOri_orientContraint' % nameInfo)
    twstOrientCntr.interpType.set(0)  # no flip or shortest
    # necessary for stretch, if not, twist joint does not follow main joints
    pm.pointConstraint(pointCnstr, twistMainJoints[0], maintainOffset=False, name='%s_twistPnt_pointConstraint' % nameInfo)
    # CreateIk
    twstIkHandle, twstIkEffector = pm.ikHandle(startJoint=twistMainJoints[0], endEffector=twistMainJoints[1], solver='ikRPsolver', name='%s_twist_ikHandle' % nameInfo)
    pointCnstr.addChild(twstIkHandle)
    # set Polevector to 0 0 0
    for axis in ('X', 'Y', 'Z'):
        twstIkHandle.attr('poleVector%s' % axis).set(0)

    #multiply x2 rotation
    multiplyX2 = pm.createNode('multiplyDivide', name='%s_twist_X2_multiplyDivide' % nameInfo)
    multiplyX2.input2X.set(2)
    trackGroup.rotateX.connect(multiplyX2.input1X)

    # nodes and connect to twist nodes rotations
    twstMultiplyDivide = pm.createNode('multiplyDivide', name='%s_twist_multiplyDivide' % nameInfo)
    twstMultiplyDivide.input2X.set(len(twistMainJoints) - 1)
    twstMultiplyDivide.operation.set(2)  # dividsion
    multiplyX2.outputX.connect(twstMultiplyDivide.input1X)
    # connect node to twist joint
    for k, twstJoint in enumerate(twistMainJoints):
        if k == 0:  # first joint nothing
            continue
        twstMultiplyDivide.outputX.connect(twstJoint.rotateX)


def stretchCurveVolume(curve, joints, baseName, main=None):
    """
    Stretch neck head
    :param curve:
    :param joints:
    :param baseName:
    :param main:
    :return:
    """
    curveInfo = pm.createNode('curveInfo', name='%s_curveInfo' % baseName)
    scaleCurveInfo = pm.createNode('multiplyDivide', name='%s_scaleCurve_curveInfo' % baseName)
    scaleCurveInfo.operation.set(2)  # divide
    # connect to scale compensate
    curveInfo.arcLength.connect(scaleCurveInfo.input1X)
    main.scaleX.connect(scaleCurveInfo.input2X)

    curve.worldSpace[0].connect(curveInfo.inputCurve)
    spineCurveLength = curve.length()

    # influence
    # create anim curve to control scale influence
    # maybe this is better to do with a curveAttr
    scaleInfluenceCurve = pm.createNode('animCurveTU', name='%s_stretch_animCurve' % baseName)
    scaleInfluenceCurve.addKeyframe(0, 0.0)
    scaleInfluenceCurve.addKeyframe(len(joints) // 2, 1.0)
    scaleInfluenceCurve.addKeyframe(len(joints) - 1, 0.0)

    for n, joint in enumerate(joints):
        jointNameSplit = str(joint).split('_')[1]

        multiplyDivide = pm.createNode('multiplyDivide', name='%s_%s_stretch_multiplyDivide' % (baseName, jointNameSplit))
        multiplyDivide.operation.set(2)  # divide
        multiplyDivide.input1X.set(spineCurveLength)
        scaleCurveInfo.outputX.connect(multiplyDivide.input2X)
        plusMinusAverage = pm.createNode('plusMinusAverage', name='%s_plusMinusAverage' % baseName)
        multiplyDivide.outputX.connect(plusMinusAverage.input1D[0])
        plusMinusAverage.input1D[1].set(-1)
        multiplyDivideInfluence = pm.createNode('multiplyDivide', name='%s_%s_stretch_multiplyDivide' % (baseName, jointNameSplit))
        plusMinusAverage.output1D.connect(multiplyDivideInfluence.input1X)
        # frame cache
        frameCache = pm.createNode('frameCache', name='%s_%s_stretch_frameCache' % (baseName, jointNameSplit))
        scaleInfluenceCurve.output.connect(frameCache.stream)
        frameCache.varyTime.set(n)
        frameCache.varying.connect(multiplyDivideInfluence.input2X)
        # plus 1
        plusMinusAverageToJoint = pm.createNode('plusMinusAverage', name='%s_%s_stretch_plusMinusAverage' % (baseName, jointNameSplit))
        multiplyDivideInfluence.outputX.connect(plusMinusAverageToJoint.input1D[0])
        plusMinusAverageToJoint.input1D[1].set(1)

        # connect to joint
        # connect if does not have connection
        for scaleAxs in (['scaleY', 'scaleZ']):
            if not joint.attr(scaleAxs).inputs():
                plusMinusAverageToJoint.output1D.connect(joint.attr(scaleAxs))


def twistJointBendingBoneConnect(parent, mainJointList, twistList, joints, twistSyncJoints, chName, zone, side,  NameIdList, path=None):
    """
    TODO: make this method?
    TODO: controller with a circle, not load controller
    Create necessary connections to use Twist joints like bending joints
    ARGS:
        parent(pm.Transform): parent of the system p.e: hipsIk_ctr
        mainJointList(List): Main joints, general 3 joints
        mainJointList(list): [[TwsA1, TwsA2,..],[TwsB1, TwsB2,..],...] same len than MainJointList
        joints(list): skined joints list, no twists p.e: upperLeg, lowerLeg, leg_End
        twistSyncJoints(List): Twist skinnedJoints, sync  with joints like: [[TwsA1, TwsA2,..],[TwsB1, TwsB2,..],...]
        chName: nameCharacter
        zone: zoneOf system
        NameIdList: names List of the specific parts
        path(str): path with character content, like controllers.json
    """
    pointColor = 7 if side == 'left' else 5
    # connect to deform skeleton review parent
    # conenct with twist joints
    pointControllers = []
    for i, joint in enumerate(mainJointList):
        aimPointList = []
        if len(twistList) > i:  # exclude last twist joint, empty items of a list
            for j, twistJnt in enumerate(twistList[i]):  # exclude first term review?
                # leg joint or specific twist
                skinJoint = joints[i] if j == 0 else twistSyncJoints[i][j - 1]  # skined joints

                nametype = 'main' if j == 0 else 'twist%s' % j
                # orient and scale
                aimGrp = pm.group(empty=True, name=str(skinJoint).replace('joint', 'main'))
                pm.xform(aimGrp, ws=True, m=pm.xform(skinJoint, ws=True, q=True, m=True))

                # connect orient to deform joints
                pm.orientConstraint(aimGrp, skinJoint, maintainOffset=False)

                twistJnt.scaleY.connect(skinJoint.scaleY)
                twistJnt.scaleZ.connect(skinJoint.scaleZ)

                aimPointList.append(aimGrp)

                # points two first
                if (i == 0 and j == 0):  # first joints
                    parent.addChild(aimGrp)

                elif (i == len(twistList) - 1 and j == len(twistList[i]) - 1):
                    # last joints
                    twistJnt.addChild(aimGrp)
                    pm.aimConstraint(aimGrp, aimPointList[-2], aimVector=(skinJoint.translateX.get(), 0, 0),
                                     worldUpType='objectrotation', worldUpObject=pointControllers[-1])


                elif i > 0 and j == 0:  # first joint not first twist chain
                    pointController = pointControllers[-1]
                    pointController.addChild(aimGrp)

                else:
                    if path:
                        pointController = createController('%s_%s_%s_%s_%s_ctr' % (chName, nametype, zone, side, NameIdList[i]), '%sTwistPoint_%s' % (zone, side), chName, path, 1, pointColor)
                    else:
                        pointController = pm.circle(name='%s_%s_%s_%s_%s_ctr' % (chName, nametype, zone, side, NameIdList[i]), r=10)[0]  # if not path, controller is a circle

                    pointController, rootPointController, pointConstraint = jointPointToController([twistJnt], pointController)
                    joint.addChild(rootPointController[0])
                    pointController = pointController[0]
                    pointControllers.append(pointController)  # save to list
                    pointController.addChild(aimGrp)
                    # aim constraint
                    if (j == 1):  # second joint, worldup object parent ctr
                        pm.aimConstraint(aimGrp, aimPointList[-2], aimVector=(skinJoint.translateX.get(), 0, 0),
                                         worldUpType='objectrotation', worldUpObject=twistList[i][0])
                    else:
                        pm.aimConstraint(aimGrp, aimPointList[-2], aimVector=(skinJoint.translateX.get(), 0, 0),
                                         worldUpType='objectrotation', worldUpObject=pointControllers[-2])

                pm.pointConstraint(aimGrp, skinJoint, maintainOffset=True, name='%s_%s_%s_%s_%s_pointConstraint' % ( chName, nametype, zone, side, NameIdList[i]))


def twistJointConnect(mainJointList, twistList, joints, twistSyncJoints):
    """
    Connect control rig twistJoints to skin joints:
    ARGS:
        mainJointList(List): Main joints, general 3 joints
        mainJointList(list): [[TwsA1, TwsA2,..],[TwsB1, TwsB2,..],...] same len than MainJointList
        joints(list): skined joints list, no twists p.e: upperLeg, lowerLeg, leg_End
        twistSyncJoints(List): Twist skinnedJoints, sync  with joints like: [[TwsA1, TwsA2,..],[TwsB1, TwsB2,..],...]
    TODO: make this method?

    """
    for i, joint in enumerate(mainJointList):
        if len(twistList) > i:  # exclude last twist joint, empty items of a list
            for j, twistJnt in enumerate(twistList[i]):  # exclude first term review?
                # leg joint or specific twist
                skinJoint = joints[i] if j == 0 else twistSyncJoints[i][j - 1]  # skined joints

                # orient and scale
                twistJnt.scaleY.connect(skinJoint.scaleY)
                twistJnt.scaleZ.connect(skinJoint.scaleZ)

                # connect orient and point to deform
                twistJnt.rename(str(skinJoint).replace('joint', 'main'))
                pm.orientConstraint(twistJnt, skinJoint, maintainOffset=False)
                pm.pointConstraint(twistJnt, skinJoint, maintainOffset=False)


def attrBlending(ikNode, fkNode, blendAttr, nameInfo, *args):
    """
    TODO: pass this func to ARHelper
    create circuitry nodes to blend ik value to fk value
    Args:
        ikNode(pm.dependNode): node with stretch ik values
        fkNode(pm.dependNode): node with stretch Fk values
        blendAttr: attribute that will direct the blend
        nameInfo: str  with name info p.e('akona_lowerLeg_leg')
        args(pm.attributes): attributes to connect with the blend. pe. mainJoint.translateX (pm object)
    Return:
        last node with the blend info
    """
    # TODO: name scalable
    ikOutputType = 'outputX' if isinstance(ikNode, pm.nodetypes.MultiplyDivide) else 'distance' if isinstance(
        ikNode, pm.nodetypes.DistanceBetween) else 'output1D'
    fKoutputType = 'outputX' if isinstance(fkNode, pm.nodetypes.MultiplyDivide) else 'distance' if isinstance(
        fkNode, pm.nodetypes.DistanceBetween) else 'output1D'

    plusMinusBase = pm.createNode('plusMinusAverage', name='%s_blending_plusMinusAverage' % nameInfo)
    plusMinusBase.operation.set(2)  # substract
    ikNode.attr(ikOutputType).connect(plusMinusBase.input1D[0])
    fkNode.attr(fKoutputType).connect(plusMinusBase.input1D[1])
    # multiply
    multiplyNode = pm.createNode('multiplyDivide', name='%s_blending_multiplyDivide' % nameInfo)
    blendAttr.connect(multiplyNode.input1X)
    plusMinusBase.output1D.connect(multiplyNode.input2X)
    # plus Fk
    plusIkFkBlend = pm.createNode('plusMinusAverage', name='%s_blendingPlusFk_plusMinusAverage' % nameInfo)
    multiplyNode.outputX.connect(plusIkFkBlend.input1D[0])
    fkNode.attr(fKoutputType).connect(plusIkFkBlend.input1D[1])

    # connect to main attributes
    for arg in args:
        plusIkFkBlend.output1D.connect(arg)

    return plusIkFkBlend
