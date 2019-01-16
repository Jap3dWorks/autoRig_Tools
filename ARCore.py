import pymel.core as pm
from maya import cmds
from maya import OpenMaya
from maya import OpenMayaAnim
import ctrSaveLoadToJson

import logging
logging.basicConfig()
logger = logging.getLogger('ARCore:')
logger.setLevel(logging.DEBUG)


def createRoots(listObjects, suffix='root'):
    """
    Create root on elements, respecting their present hierarchy.
    Args:
        listObjects(list)(pm.Transform)(pm.Joint): list of transforms to create root, on joints set joint orient to 0
        suffix(str): suffix for the root grp

    Returns:
        roots(list): list of roots
    """
    roots = []
    for arg in listObjects:
        try:
            parent = arg.firstParent()
        except:
            parent = None
        # explanation: pm getTransformation gives transform matrix in object space.
        # so we need to use pm.xform()
        rootGrp = pm.group(em=True, name='%s_%s' % (arg, suffix))
        matrixTransform = pm.xform(arg, q=True, ws=True, m=True)
        pm.xform(rootGrp, ws=True, m=matrixTransform)

        if parent:
            parent.addChild(rootGrp)
        rootGrp.addChild(arg)

        # if is a joint, assegure reset values
        if isinstance(arg, pm.nodetypes.Joint):
            for axis in ('X', 'Y', 'Z'):
                arg.attr('jointOrient%s' % axis).set(0.0)

            arg.setRotation((0,0,0), 'object')

        roots.append(rootGrp)

    return roots

def createController (name, controllerType, chName, path, scale=1.0, colorIndex=4):
    """
    Args:
        name: name of controller
        controllerType(str): from json controller types
        chName: name of json file
        path: path where is json file
    return:
        controller: pymel transformNode
        transformMatrix: stored position
    """
    controller, transformMatrix = ctrSaveLoadToJson.SaveLoadControls.ctrLoadJson(controllerType, chName, path, scale, colorIndex)
    controller = pm.PyNode(controller)
    controller.rename(name)

    shapes = controller.listRelatives(s=True)
    # hide shape attr
    for shape in shapes:
        for attr in ('aiRenderCurve', 'aiCurveWidth', 'aiSampleRate', 'aiCurveShaderR', 'aiCurveShaderG', 'aiCurveShaderB'):
            pm.setAttr('%s.%s' % (str(shape), attr), channelBox=False, keyable=False)

    pm.xform(controller, ws=True, m=transformMatrix)
    return controller

def jointPointToController(joints, controller):
    """
    TODO: input scale too. first read if scale is connected to something, if it is, combine
    create a controller, create a root for the controller and point constraint to joint
    Args:
        joints(list(Joint)): joint where create controller
        controller(Transform): controller object
    Returns:
        list: [controller], [root], [pointConstraint]
    """
    controllerList = []
    rootList = []
    pointConstraintList=[]
    aimGrpList = []
    for i, joint in enumerate(joints):
        if i == 0:
            controllerDup = controller
        else:
            controllerDup = controller.duplicate()[0]

        pm.xform(controllerDup, ws=True, m=pm.xform(joint, ws=True, q=True, m=True))
        controllerRoot = createRoots([controllerDup])[0]
        # point constraint
        parentConstraint = pm.parentConstraint(joint, controllerRoot)

        # append to lists
        controllerList.append(controllerDup)
        rootList.append(controllerRoot)
        pointConstraintList.append(parentConstraint)
        # lock attr
        lockAndHideAttr(controllerDup, False, False, True)
        for axis in ('Y', 'Z'):
            controllerDup.attr('rotate%s' % axis).lock()
            pm.setAttr('%s.rotate%s' % (str(controllerDup), axis), channelBox=False, keyable=False)

    return controllerList, rootList, pointConstraintList

def lockAndHideAttr(obj, translate=False, rotate=False, scale=False):
    """
    lock and hide transform attributes
    # TODO: add limit operations
    Args:
        obj(pm.Trasform): Element to lock and hide
        translate(True): true, lock and hide translate
        rotate(True): true, lock and hide rotate
        scale(True): true, lock and hide scale
    """
    if isinstance(obj, list):
        itemList = obj
    else:
        itemList = []
        itemList.append(obj)

    for item in itemList:
        if translate:
            item.translate.lock()
            for axis in ('X', 'Y', 'Z'):
                pm.setAttr('%s.translate%s' % (str(item), axis), channelBox=False, keyable=False)
        if rotate:
            item.rotate.lock()
            for axis in ('X', 'Y', 'Z'):
                pm.setAttr('%s.rotate%s' % (str(item), axis), channelBox=False, keyable=False)
        if scale:
            item.scale.lock()
            for axis in ('X', 'Y', 'Z'):
                pm.setAttr('%s.scale%s' % (str(item), axis), channelBox=False, keyable=False)

def arrangeListByHierarchy(itemList):
    """
    Arrange a list by hierarchy
    p.e [[toea1, toea2, ...], [toeb, toeb_tip]]
    Args:
        itemList:
    Returns(list(list)): final list
    """
    def hierarchySize(obj):
        # key func for sort
        fullPath = obj.fullPath()
        sizeFullPath = fullPath.split('|')
        return len(sizeFullPath)

    toesJointsCopy = list(itemList)  # copy of the toes list
    toesJointsArr = []
    while len(toesJointsCopy):
        toeJoint = []
        firstJoint = toesJointsCopy.pop(0)
        toeJoint.append(firstJoint)
        for joint in firstJoint.listRelatives(ad=True):
            if joint in toesJointsCopy:
                toeJoint.append(joint)
                toesJointsCopy.remove(joint)

        # sort the list to assure a good order
        toesJointsArr.append(sorted(toeJoint, key=hierarchySize))
    logger.debug('arrangeListByHierarchy: sorted: %s' % toesJointsArr)

    return toesJointsArr

def attrBlending(ikNode, fkNode, blendAttr, nameInfo, *args):
    """
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
    ikOutputType = 'outputX' if isinstance(ikNode, pm.nodetypes.MultiplyDivide) else 'distance' if isinstance(ikNode, pm.nodetypes.DistanceBetween) else 'output1D'
    fKoutputType = 'outputX' if isinstance(fkNode, pm.nodetypes.MultiplyDivide) else 'distance' if isinstance(fkNode, pm.nodetypes.DistanceBetween) else 'output1D'

    plusMinusBase=pm.createNode('plusMinusAverage', name='%s_blending_plusMinusAverage' % nameInfo)
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

def stretchIkFkSetup(fkObjList, fkDistances, nodeAttr, ikObjList, ikDistance, ikJoints, mainJoints, twsitMainJoints, nameInfo, main, poleVector=None):
    """
    create ik and fk stretch system with twistJoints, stretching by translate
    some lists must be of the same len()
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
    conditionalScaleFactor = pm.createNode('condition', name='%s_ikStretch_stretchValue_conditional' % nameInfo)  # review stretchValue
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
        nameInfo: list of three elements with name info p.e('akona', 'leg', 'lowerLeg')

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


def calcDistances(pointList,vector=False):
    """
    Calculate de distance between the points in the given list. 0->1, 1->2, 2->3...
    Args:
        pointList(List)(pm.Transform):
        vector(bool): true: use vectors to calculate distances. False: read x value of each element. if points are joints, better use False
    Returns:
        (list): with distances
        (float): total distance
    """
    distancesList = []
    totalDistance = 0
    if vector:
        for i, point in enumerate(pointList):
            if i == len(pointList)-1:
                continue
            point1 = point.getTranslation('world')
            point2 = pointList[i+1].getTranslation('world')

            vector = point2 - point1
            vector = OpenMaya.MVector(vector[0],vector[1],vector[2])
            # length of each vector
            length = vector.length()

            distancesList.append(vector.length())
            totalDistance += length

    else:  # simply read X values
        for point in pointList[1:]:
            xtranslateValue = point.translateX.get()
            totalDistance += xtranslateValue
            distancesList.append(xtranslateValue)

    return distancesList, totalDistance


def syncListsByKeyword(primaryList, secondaryList, keyword=None):
    """
    arrange the secondary list by each element on the primary, if they are equal less the keyword
    if not keyword, the script will try to find one, p.e:
    list1 = ['akona_upperArm_left_joint','akona_foreArm_left_joint','akona_arm_end_left_joint']
    list2 = ['akona_upperArm_twist1_left_joint','akona_upperArm_twist2_left_joint','akona_foreArm_twist1_left_joint', 'akona_foreArm_twist2_left_joint']
    keyword: twist
    Returnsn : [['akona_upperArm_twist1_left_joint', 'akona_upperArm_twist2_left_joint'], ['akona_foreArm_twist1_left_joint', 'akona_foreArm_twist2_left_joint'], []]

    """
    filterChars = '1234567890_'
    # if not keyword try to find one
    if not keyword:
        count = {}
        # count how many copies of each word we have, using a dictionary
        for secondaryItem in secondaryList:
            for word in str(secondaryItem).split('_'):
                for fChar in filterChars:
                    word = word.replace(fChar, '')
                # if word is yet in dictionary, plus one, if not, create key with word and set it to one
                # explanation: dict.get(word, 0) return the value of word, if not, return 0
                count[word] = count.get(word, 0) + 1
        # key word must not be in primary list
        wordsDetect = [word for word in count if count[word] == len(secondaryList) and word not in str(primaryList[0])]

        if len(wordsDetect) != 1:
            logger.info('no keyword detect')
            return
        keyword = wordsDetect[0]

    arrangedSecondary = []
    # arrange by keyword
    for primaryItem in primaryList:
        actualList = []
        for secondaryItem in secondaryList:
            splitStr = str(secondaryItem).partition(keyword)
            indexCut = None
            for i, char in enumerate(splitStr[-1]):
                if char in filterChars:
                    indexCut = i + 1
                else:
                    break

            compareWord = splitStr[0] + splitStr[-1][indexCut:]
            if compareWord == str(primaryItem):
                actualList.append(secondaryItem)

        arrangedSecondary.append(actualList)

    return arrangedSecondary


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


def relocatePole(pole, joints, distance=1):
    """
    relocate pole position for pole vector
    at the moment, valid for 3 joints.
    not calculate rotation
    Args:
        pole(pm.Transform): PyNode of pole
        joints(list)(pm.Transform): list of joints, pm nodes
        distance(float): distance from knee
    """
    # first vector
    position1 = joints[0].getTranslation('world')
    position2 = joints[1].getTranslation('world')
    vector1 = OpenMaya.MVector(position2[0]-position1[0],position2[1]-position1[1],position2[2]-position1[2])
    vector1.normalize()

   # second vector
    position1 = joints[-1].getTranslation('world')
    position2 = joints[-2].getTranslation('world')
    vector2 = OpenMaya.MVector(position2[0]-position1[0],position2[1]-position1[1],position2[2]-position1[2])
    vector2.normalize()

    # z vector
    poleVector = (vector1 + vector2)
    poleVector.normalize()

    # x vector cross product
    xVector = vector2 ^ poleVector
    xVector.normalize()

    # y vector cross product
    yVector = poleVector ^ xVector
    yVector.normalize()

    pole.setTransformation([xVector.x, xVector.y, xVector.z, 0, yVector.x, yVector.y, yVector.z, 0, poleVector.x, poleVector.y, poleVector.z, 0,
                       poleVector.x * distance + position2[0], poleVector.y * distance + position2[1], poleVector.z * distance + position2[2], 1])



def snapCurveToPoints(points, curve, iterations=4, precision=0.05):
    """
    Snap curve to points moving CV's of the nurbsCurve
    Args:
        points(list): transform where snap curve
        curve(pm.nurbsCurve): curve to snap
        iterations(int): number of passes, higher more precise. default 4
        precision(float): distance between point and curve the script is gonna take as valid. default 0.05
    """
    selection = OpenMaya.MSelectionList()
    selection.add(str(curve))
    dagpath = OpenMaya.MDagPath()
    selection.getDagPath(0, dagpath)

    mfnNurbsCurve = OpenMaya.MFnNurbsCurve(dagpath)

    for i in range(iterations):
        for joint in points:
            jointPos = joint.getTranslation('world')
            jointPosArray = OpenMaya.MFloatArray()
            util = OpenMaya.MScriptUtil()
            util.createFloatArrayFromList(jointPos, jointPosArray)

            mPoint = OpenMaya.MPoint(jointPosArray[0], jointPosArray[1], jointPosArray[2], 1)
            closestPointCurve = mfnNurbsCurve.closestPoint(mPoint, None, 1, OpenMaya.MSpace.kWorld)

            mvector = OpenMaya.MVector(mPoint - closestPointCurve)

            if mvector.length() < precision:
                continue

            # nearest cv
            cvArray = OpenMaya.MPointArray()
            mfnNurbsCurve.getCVs(cvArray, OpenMaya.MSpace.kWorld)
            nearest = []
            lastDistance = None

            for n in range(mfnNurbsCurve.numCVs()):
                if n == 0 or n == cvArray.length() - 1:
                    continue

                distance = mPoint.distanceTo(cvArray[n])

                if not nearest or distance < lastDistance:
                    nearest = []
                    nearest.append(cvArray[n])
                    nearest.append(n)

                    lastDistance = distance

            mfnNurbsCurve.setCV(nearest[1], nearest[0] + mvector, OpenMaya.MSpace.kWorld)

    mfnNurbsCurve.updateCurve()

def orientToPlane(matrix, plane=None, respectAxis=None):
    """
    Conserve the general orient of a matrixTransform, but aligned to a plane.
    option to select the respect axis
    Args:
        controller(pm.transform): transform matrix
        plane(string): zx, xy, yz  lower case, first vector is the prefered vector
    """
    if not plane:
        logger.info('no plane')
        return matrix
    elif len(plane) > 2:
        logger.info('insert a valid plane')
        return matrix

    axisList = 'xyz'

    vectors = {}
    vIndex = 0
    # store initial vectors
    for axis in axisList:
        vectors[axis] = OpenMaya.MVector(matrix[vIndex], matrix[vIndex+1], matrix[vIndex+2])
        vIndex += 4

    # compare dot products, and find the nearest vector to plane vector
    planeVector = [0 if axis in plane else 1 for axis in axisList]  # plane vector (1,0,0) or (0,1,0) or (0,0,1)
    planeVector = OpenMaya.MVector(planeVector[0], planeVector[1], planeVector[2])
    dotValue = None
    respectVector=None
    for axis in axisList:
        newDot = abs(planeVector * vectors[axis])
        if dotValue < newDot:
            dotValue = newDot
            respectVector = axis

    # find resettable axis
    resetAxis = axisList  # convert axis list in axis string
    for axis in plane:
        resetAxis = resetAxis.replace(axis, '')

    # reset the axis
    resetPlane=''
    for key, vector in vectors.iteritems():
        if key == respectVector:  # this is not necessary to reset
            continue
        setattr(vector, resetAxis, 0)
        vector.normalize()
        resetPlane += key  # edited vectors, projected over the plane

    # reconstruct matrix
    # use comapreVectors to avoid negative scales, comparing dot product
    compareVector = OpenMaya.MVector(vectors[respectVector])
    vectors[respectVector] = vectors[resetPlane[0]] ^ vectors[resetPlane[1]]
    if vectors[respectVector] * compareVector < 0:  # if dot negative, it will get as result a negative scale
        vectors[respectVector] = vectors[resetPlane[1]] ^ vectors[resetPlane[0]]
    vectors[respectVector].normalize()  # normalize
    compareVector = OpenMaya.MVector(vectors[resetPlane[1]])
    vectors[resetPlane[1]] = vectors[respectVector] ^ vectors[resetPlane[0]]
    if compareVector * vectors[resetPlane[1]] < 0:
        vectors[resetPlane[1]] = vectors[resetPlane[0]] ^ vectors[respectVector]
    vectors[resetPlane[1]].normalize()  # normalize

    returnMatrix = [vectors[axisList[0]].x, vectors[axisList[0]].y, vectors[axisList[0]].z, matrix[3], vectors[axisList[1]].x, vectors[axisList[1]].y, vectors[axisList[1]].z, matrix[7],
                vectors[axisList[2]].x, vectors[axisList[2]].y, vectors[axisList[2]].z, matrix[11], matrix[12], matrix[13], matrix[14], matrix[15]]

    return returnMatrix


def stretchCurveVolume(curve, joints, nameInfo, main=None):
    """
    Stretch neck head
    :param curve:
    :param joints:
    :param nameInfo:
    :param main:
    :return:
    """
    curveInfo = pm.createNode('curveInfo', name='%s_curveInfo' % nameInfo)
    scaleCurveInfo = pm.createNode('multiplyDivide', name='%s_scaleCurve_curveInfo' % nameInfo)
    scaleCurveInfo.operation.set(2)  # divide
    # connect to scale compensate
    curveInfo.arcLength.connect(scaleCurveInfo.input1X)
    main.scaleX.connect(scaleCurveInfo.input2X)

    curve.worldSpace[0].connect(curveInfo.inputCurve)
    spineCurveLength = curve.length()

    # influence
    # create anim curve to control scale influence
    # maybe this is better to do with a curveAttr
    scaleInfluenceCurve = pm.createNode('animCurveTU', name='%s_stretch_animCurve' % nameInfo)
    scaleInfluenceCurve.addKeyframe(0, 0.0)
    scaleInfluenceCurve.addKeyframe(len(joints) // 2, 1.0)
    scaleInfluenceCurve.addKeyframe(len(joints) - 1, 0.0)

    for n, joint in enumerate(joints):
        jointNameSplit = str(joint).split('_')[1]

        multiplyDivide = pm.createNode('multiplyDivide', name='%s_%s_stretch_multiplyDivide' % (nameInfo, jointNameSplit))
        multiplyDivide.operation.set(2)  # divide
        multiplyDivide.input1X.set(spineCurveLength)
        scaleCurveInfo.outputX.connect(multiplyDivide.input2X)
        plusMinusAverage = pm.createNode('plusMinusAverage', name='%s_plusMinusAverage' % nameInfo)
        multiplyDivide.outputX.connect(plusMinusAverage.input1D[0])
        plusMinusAverage.input1D[1].set(-1)
        multiplyDivideInfluence = pm.createNode('multiplyDivide', name='%s_%s_stretch_multiplyDivide' % (nameInfo, jointNameSplit))
        plusMinusAverage.output1D.connect(multiplyDivideInfluence.input1X)
        # frame cache
        frameCache = pm.createNode('frameCache', name='%s_%s_stretch_frameCache' % (nameInfo, jointNameSplit))
        scaleInfluenceCurve.output.connect(frameCache.stream)
        frameCache.varyTime.set(n)
        frameCache.varying.connect(multiplyDivideInfluence.input2X)
        # plus 1
        plusMinusAverageToJoint = pm.createNode('plusMinusAverage', name='%s_%s_stretch_plusMinusAverage' % (nameInfo, jointNameSplit))
        multiplyDivideInfluence.outputX.connect(plusMinusAverageToJoint.input1D[0])
        plusMinusAverageToJoint.input1D[1].set(1)

        # connect to joint
        # connect if does not have connection
        for scaleAxs in (['scaleY', 'scaleZ']):
            if not joint.attr(scaleAxs).inputs():
                plusMinusAverageToJoint.output1D.connect(joint.attr(scaleAxs))


def connectAttributes(driver, driven, attributes, axis):
    """
    connect the attributes of the given objects
    Args:
        driver: source of the connection
        driven: destiny of the connection
        attributes: attributes to connect p.e scale, translate
        axis: axis of the attribute p.e ['X', 'Y', 'Z'] or XYZ
    """
    for attribute in attributes:
        for axi in axis:
            driver.attr('%s%s' % (attribute, axi)).connect(driven.attr('%s%s' % (attribute, axi)))


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

def getSkinedMeshFromJoint(joint):
    """
    Find meshes affected by the joint
    :param joint (pm or str): joint
    :return (set): Meshes affected by the joint
    """
    # create pm objects from list
    joint = pm.PyNode(joint) if isinstance(joint, str) else joint
    # find skin clusters
    skinClusterLst = set(joint.listConnections(type='skinCluster'))

    meshes = []
    for skin in skinClusterLst:
        meshes += skin.getGeometry()

    return set(meshes)

def vertexIntoCurveCilinder(mesh, curve, distance, minParam=0, maxParam=1):
    """
    Return a list of vertex index inside cilinder defined by a curve
    :param mesh(str): mesh shape
    :param curve(str): curve shape
    :param distance(float):
    :return: List with vertex indexes
    """
    # use the API, Faster for this type of operations
    mSelection = OpenMaya.MSelectionList()
    mSelection.add(mesh)
    mSelection.add(curve)

    # MDagObject to query worldSpace deforms
    # mesh
    meshDagPath = OpenMaya.MDagPath()
    mSelection.getDagPath(0, meshDagPath)
    meshVertIt = OpenMaya.MItMeshVertex(meshDagPath)  # vertexIterator
    # curve
    curveDagPath = OpenMaya.MDagPath()
    mSelection.getDagPath(1, curveDagPath)
    curveMFn = OpenMaya.MFnNurbsCurve(curveDagPath)

    # minParam MaxParam adjust to maxValue of the curve
    maxParam = cmds.getAttr('%s.maxValue' % curve)*maxParam
    minParam = cmds.getAttr('%s.maxValue' % curve)*minParam + cmds.getAttr('%s.minValue' % curve)

    # mscriptUtil
    util = OpenMaya.MScriptUtil()
    vertexIndexes = []  # store vertex indexes
    while not meshVertIt.isDone():
        # store vertex position
        vertexPosition = meshVertIt.position(OpenMaya.MSpace.kWorld)
        # point on curve
        ptr = util.asDoublePtr()
        curveMFn.closestPoint(vertexPosition, ptr, 0.1, OpenMaya.MSpace.kWorld)  # review param (False, ptr)
        param = util.getDouble(ptr)
        # param control
        param = max(minParam, min(maxParam, param))

        # recalculate from param
        pointCurve = OpenMaya.MPoint()
        curveMFn.getPointAtParam(param, pointCurve)

        # define vector
        vertexVector = OpenMaya.MVector(vertexPosition-pointCurve)
        # check distance from the curve
        if vertexVector.length() < distance:
            tangent = curveMFn.tangent(param, OpenMaya.MSpace.kWorld)  # get param tangent
            # dot product
            dotProduct = vertexVector*tangent
            # let some precision interval
            if not (dotProduct > 0.1 or dotProduct < -0.1):
                vertexIndexes.append(meshVertIt.index())

        meshVertIt.next()

    return vertexIndexes

def smoothDeformerWeights(deformer):
    """
    smooth deformer weights.
    :param deformer(str): Deformer name
    """
    mSelection = OpenMaya.MSelectionList()
    mSelection.add(deformer)
    # deformer
    deformerMObject = OpenMaya.MObject()
    mSelection.getDependNode(0, deformerMObject)

    # documentation: https://groups.google.com/forum/#!topic/python_inside_maya/E7QirW4Z0Nw
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
    weightGeometryFilter.getWeights(0, components, originalWeight)

    # mesh
    meshVertIt = OpenMaya.MItMeshVertex(dagPathComponents)


    newWeights = OpenMaya.MFloatArray()
    # calculate new weights
    while not meshVertIt.isDone():
        # TODO: pure API
        index = meshVertIt.index()
        connectedVertices = OpenMaya.MIntArray()
        meshVertIt.getConnectedVertices(connectedVertices)

        averageValue = originalWeight[index]
        for vertex in connectedVertices:
            averageValue += originalWeight[vertex]

        newWeights.append(averageValue/(connectedVertices.length()+1))

        meshVertIt.next()

    # set new weights
    weightGeometryFilter.setWeight(dagPathComponents, components, newWeights)


def setWireDeformer(joints, mesh=None, nameInfo=None, curve=None, weights=None):
    """
    Create a curve and wire deformer using joint position as reference
    :param joints(pm or str): joints
        mesh(list): list of meshes wire will affect
    :return: wire deformer and created curve
    nameInfo: characterName_zone_side
    """
    # create pm objects from list
    joints = [pm.PyNode(joint) if isinstance(joint, str) else joint for joint in joints]

    # get points
    points = [joint.getTranslation('world') for joint in joints]
    logger.debug('Wire Deformer curve points: %s' % points)

    # If curve arg is None, create a two point curve
    if not curve:
        curve = pm.curve(ep=[points[0], points[-1]], d=2, name=str(nameInfo)+'_wire_curve')
        # adjust curve points
        snapCurveToPoints(joints, curve)

    # if not mesh arg, get a random mesh trough the skinCluster
    if not mesh:
        mesh = getSkinedMeshFromJoint(joints[0]).pop()
    else:
        # check type node
        if isinstance(mesh, str):
            mesh = pm.PyNode(mesh)
        if isinstance(mesh, pm.nodetypes.Transform):
            mesh = mesh.getShape()

    # get affected vertex
    affectedVertex = vertexIntoCurveCilinder(str(mesh), str(curve.getShape()), 15, .05, .98)

    # create wire deformer
    wire, wireCurve = pm.wire(mesh, gw=False, w=curve, dds=(0, 40))
    logger.debug('wire curve: %s' % wireCurve)
    pm.percent(wire, mesh, v=0)
    for index in affectedVertex:
        pm.percent(wire, mesh.vtx[index], v=1)

    # copyDeformerWeights  ->  command for copy, mirror deformer weights
    # smooth weights
    for i in range(4):
        smoothDeformerWeights(str(wire))

    return wire, curve

def TransformCurveCVCtr(curve):
    """
    Connect transformations to each curve control point
    :param curve(str or pm):
    :return (list): list with created transformations
    """
    # check curve type data
    if isinstance(curve, str):
        curve = pm.PyNode(curve)
    if isinstance(curve, pm.nodetypes.Transform):
        curve = curve.getShape()

    transforms = []
    for n, point in enumerate(curve.getCVs()):
        transform = pm.group(empty=True)
        transform.setTranslation(point)
        decomposeMatrix = pm.createNode('decomposeMatrix')
        transform.worldMatrix[0].connect(decomposeMatrix.inputMatrix)
        decomposeMatrix.outputTranslate.connect(curve.controlPoints[n])
        transforms.append(transform)

    return transforms

def latticeBendDeformer(lattice, controller=None):
    """
    connect a bend deformer to a lattice, and the necessary nodes.
    Controller should have transforms to zero.
    :param lattice: lattice transform or shape
    :param controller: Controller for the system
    :return(list): Transform nodes created in the function:  scaleGrp, referenceBase, referenceController, bendTransform,
    :return: controllerRoot
    """
    # TODO: test with non world aligned lattices
    # check data type
    # check lattice type data
    if isinstance(lattice, str):
        lattice = pm.PyNode(lattice)
    if isinstance(lattice, pm.nodetypes.Transform):
        lattice = lattice.getShape()

    #check controller type
    if isinstance(controller, str):
        controller = pm.PyNode(controller)
    if not isinstance(controller, pm.nodetypes.Transform):
        logger.info('controller must be a transform node')
        return

    latticeTransform = lattice.getTransform()
    # check lattice visibility, important to query correctly the bbox
    if not latticeTransform.visibility.get():
        latticeTransform.visibility.set(True)

    # lattice bbox
    latticeTransform = lattice.getTransform()
    latBbox = latticeTransform.boundingBox()
    logger.debug('LatBboc: %s' % latBbox)

    # Util transform  data
    centerPoint = (latBbox[0]+latBbox[1])/2
    logger.debug('Lattice center point: %s, %s' % (centerPoint, type(centerPoint)))
    # min and max centered points
    minPoint = pm.datatypes.Point(centerPoint[0], latBbox[0][1], centerPoint[2])
    maxPoint = pm.datatypes.Point(centerPoint[0], latBbox[1][1], centerPoint[2])
    latHigh = latBbox[1][1] - latBbox[0][1]

    # reposition controller
    controller.setTranslation(maxPoint, 'world')
    # root the controller
    controllerRoot = createRoots([controller])[0]

    # create bend deformer
    # review, get some warnings here, maybe cmds is a better option
    bend, bendTransform = cmds.nonLinear(str(lattice), type='bend', lowBound=-1, curvature=0)
    bendTransform = pm.PyNode(bendTransform)
    bendTransform.setTranslation(minPoint, 'world')
    cmds.setAttr('%s.lowBound' %(bend), 0)
    cmds.setAttr('%s.highBound' % (bend), 1)
    # set scale lattice
    bendTransform.scale.set([latHigh,latHigh,latHigh])

    ## create nodes ##
    distanceBettween = pm.createNode('distanceBetween')
    distanceBettween.point2.set([0,0,0])
    # don't connect y component
    for axis in ('X', 'Z'):
        controller.attr('translate%s' % axis).connect(distanceBettween.attr('point1%s' % axis))

    # condition, to avoid vector with length 0
    condition = pm.createNode('condition')
    distanceBettween.distance.connect(condition.firstTerm)
    conditionAxis=['R','B']
    for i, axis in enumerate(['X','Z']):
        controller.attr('translate%s' % axis).connect(condition.attr('colorIfFalse%s' % conditionAxis[i]))

    condition.colorIfFalseG.set(0)
    condition.colorIfTrue.set([0.001, 0, 0])

    # normalizeVector
    normalize=pm.createNode('vectorProduct')
    normalize.operation.set(0)
    normalize.normalizeOutput.set(True)  # normalized
    condition.outColor.connect(normalize.input1)
    # find vector z, use cross product
    crossProduct = pm.createNode('vectorProduct')
    crossProduct.normalizeOutput.set(True)  # normalize
    crossProduct.operation.set(2)
    normalize.output.connect(crossProduct.input1)
    crossProduct.input2.set([0, 1, 0])
    # create fourByFour matrix
    matrix = pm.createNode('fourByFourMatrix')
    # vector X
    for i, axis in enumerate(['X', 'Y', 'Z']):
        normalize.attr('output%s' % axis).connect(matrix.attr('in0%s'% i))
    # vector Z
    for i, axis in enumerate(['X', 'Y', 'Z']):
        crossProduct.attr('output%s' % axis).connect(matrix.attr('in2%s'% i))

    # decompose Matrix
    decomposeMatrix = pm.createNode('decomposeMatrix')
    matrix.output.connect(decomposeMatrix.inputMatrix)
    # connect rotation
    decomposeMatrix.outputRotate.connect(bendTransform.rotate)

    ## curvature ##
    decomposeMatrixController = pm.createNode('decomposeMatrix')
    controller.worldMatrix.connect(decomposeMatrixController.inputMatrix)
    # transformNodes
    referenceController = pm.group(empty=True, name='%s_ctr_ref' % str(latticeTransform))
    pm.xform(referenceController, ws=True, m=pm.xform(controller, q=True, ws=True, m=True))
    referenceBase = pm.group(empty=True, name='%s_base_ref' % str(latticeTransform))
    referenceBase.setTranslation(minPoint, 'world')
    # ref Controller
    RefControllerDecMatr = pm.createNode('decomposeMatrix')
    referenceController.worldMatrix.connect(RefControllerDecMatr.inputMatrix)
    #base
    refBaseDecMatr = pm.createNode('decomposeMatrix')
    referenceBase.worldMatrix.connect(refBaseDecMatr.inputMatrix)
    # firstVector
    vector1 = pm.createNode('plusMinusAverage')
    vector1.operation.set(2)  #substract
    decomposeMatrixController.outputTranslate.connect(vector1.input3D[0])
    refBaseDecMatr.outputTranslate.connect(vector1.input3D[1])
    # second vector
    vector2 = pm.createNode('plusMinusAverage')
    vector2.operation.set(2)  #substract
    RefControllerDecMatr.outputTranslate.connect(vector2.input3D[0])
    refBaseDecMatr.outputTranslate.connect(vector2.input3D[1])
    # calculate angle
    angleBetween = pm.createNode('angleBetween')
    vector1.output3D.connect(angleBetween.vector1)
    vector2.output3D.connect(angleBetween.vector2)
    # connect to bend
    cmds.connectAttr('%s.angle' %(str(angleBetween)), '%s.curvature' % bend)

    ## scale system ##
    scaleGrp = pm.group(empty=True, name='%s_scale_grp' % str(latticeTransform))
    scaleGrp.setTranslation(minPoint, 'world')
    scaleGrp.addChild(latticeTransform)
    # node connection
    # distance between controller and base lattice
    distanceBettween = pm.createNode('distanceBetween')
    controller.worldMatrix.connect(distanceBettween.inMatrix1)
    referenceBase.worldMatrix.connect(distanceBettween.inMatrix2)
    # distance between controller REFERENCE and base lattice
    distanceReference = pm.createNode('distanceBetween')
    referenceController.worldMatrix.connect(distanceReference.inMatrix1)
    referenceBase.worldMatrix.connect(distanceReference.inMatrix2)
    # divide by the original length
    multiplyDivide = pm.createNode('multiplyDivide')
    multiplyDivide.operation.set(2)  # set to divide
    # connect distances
    distanceBettween.distance.connect(multiplyDivide.input1X)
    distanceReference.distance.connect(multiplyDivide.input2X)
    # get inverse
    inverse = pm.createNode('multiplyDivide')
    inverse.operation.set(2)  # divide
    inverse.input1X.set(1)
    multiplyDivide.outputX.connect(inverse.input2X)
    # connect result to scale group
    multiplyDivide.outputX.connect(scaleGrp.scaleY)
    for axis in ('X', 'Z'):
        inverse.outputX.connect(scaleGrp.attr('scale%s' % axis))

    # lock and hide attr
    lockAndHideAttr(controller, False, True, True)

    return [scaleGrp, referenceBase, referenceController, bendTransform, controllerRoot]

def dotBasedPS(driverVector, drivenVector):
    """
    Create a conection based on a space deform to drive attributes
    :param driverVector(str or pm): VectorProduct node with driver vector info
    :param drivenVector(str or pm): Transform node that will be used as a reference to calculate the dot product
    :param attributes(str): attributes that will be drived
    :return psDot: vector product node with dot product
    """
    # get ps dot
    psDot = pm.createNode('vectorProduct')
    psDot.operation.set(1)
    driverVector.output.connect(psDot.input2)  # connect driver vector
    drivenVector.output.connect(psDot.input1)  # connect driven vector

    return psDot


def getVectorBetweenTransforms(point1, point2, normalized=True):
    """
    Get the vector defined by two transform nodes. independent of the hierarchy
    the base of this method is set a vectorProduct node as dotMatrixProduct. and
    operate over a vector (0,0,0), this way we get the world space translation.
    :param point1: origin of the vector
    :param point2: end of the vector
    :param normalized: normalized or not
    :return:
    """
    # check data types
    if isinstance(point1, str):
        point1 = pm.PyNode(point1)
    if isinstance(point2, str):
        point2 = pm.PyNode(point2)

    # get point1 transform from transform node
    vector1Product = pm.createNode('vectorProduct')
    vector1Product.normalizeOutput.set(False)
    point1.worldMatrix[0].connect(vector1Product.matrix)
    # set vProduct node
    vector1Product.operation.set(4)
    for axis in 'XYZ':
        vector1Product.attr('input1%s' % axis).set(0)

    #get point2 Transform Node
    vector2Product = pm.createNode('vectorProduct')
    vector2Product.normalizeOutput.set(False)
    point2.worldMatrix[0].connect(vector2Product.matrix)
    # set v2Product node
    vector2Product.operation.set(4)
    for axis in 'XYZ':
        vector2Product.attr('input1%s' % axis).set(0)

    # substract vector1 from vector2
    plusMinus=pm.createNode('plusMinusAverage')
    plusMinus.operation.set(2) # substract
    vector1Product.output.connect(plusMinus.input3D[1])  # vector2 - vector1
    vector2Product.output.connect(plusMinus.input3D[0])

    # finally connect to to another vector product and normalize if arg normalize is true
    vectorBetween = pm.createNode('vectorProduct')
    vectorBetween.operation.set(0)  # no operation
    vectorBetween.normalizeOutput.set(normalized)
    plusMinus.output3D.connect(vectorBetween.input1)

    return vectorBetween


def getVectorFromMatrix(transform, vector):
    """
    Get the desired vector from a transform node
    :param transform:
    :param vector:
    :return: vectorProduct Node
    """
    # check args types and create pm nodes
    if isinstance(transform, str):
        transform = pm.PyNode(transform)

    # get Transform vector
    driverVecProduct = pm.createNode('vectorProduct')
    driverVecProduct.normalizeOutput.set(True)
    transform.worldMatrix[0].connect(driverVecProduct.matrix)
    # set Vector product to vector matrix product
    # and get x vector
    driverVecProduct.operation.set(3)  # 3 is matrix vector product
    for i, attr in enumerate('XYZ'):
        driverVecProduct.attr('input1%s' % attr).set(vector[i])
    driverVecProduct.normalizeOutput.set(True)

    return driverVecProduct

def jointChain(length=None, joints=10, curve=None):
    """
    create a joint chain
    :param distance(float): length of the chain, if curve arg is given, this param can be None
    :param joints(int): number of joints
    :param curve(str or pm): if curve, adapt joints to curve
    :return: joint list
    """
    # to avoid errors clear selection
    pm.select(cl=True)

    jointsList = []  # store joints

    # if curve arg
    if curve:
        # check type
        if isinstance(curve, str):
            curve = pm.PyNode(curve)
        if isinstance(curve, pm.nodetypes.Transform):
            curve = curve.getShape()

        # dup the curve and rebuilt it, smoother results
        curveDup = curve.duplicate()[0]
        curveDup = curveDup.getShape()
        pm.rebuildCurve(curveDup, ch=False, rpo=True, rt=False, end=True, kr=False, kep=True,
                        kt=False, s=curveDup.numCVs(), d=2, tol=0.01)

        # get max param value of the curve
        maxValue = curveDup.maxValue.get()
        incrValue = maxValue/(joints-1)  # distance increment per joint
        for i in range(joints+1):
            # create joint
            if i < joints:
                pm.select(cl=True)
                joint = pm.createNode('joint')
                joint.setTranslation(curveDup.getPointAtParam(incrValue * i, 'world'), 'world')
                pm.select(cl=True)
            if jointsList:
                # first construct matrix
                if i < joints:
                    vectorX = pm.datatypes.Vector(joint.getTranslation('world') - jointsList[-1].getTranslation('world'))
                    vectorX.normalize()
                else:
                    vectorX = curveDup.tangent(incrValue*(i-1), 'world')

                # if the curve do not has curvature, normal method will give us an error
                try:
                    vectorY = curveDup.normal(incrValue*(i-1), 'world')
                except:
                    # if it is the case, construct a basic vector
                    vectorY = pm.datatypes.Vector([0,1,0])
                    # while dot != 0 the vector isn't perpendicular
                    if vectorX * vectorY != 0:
                        # so we force a zero dot. dot formula: v1.x*v2.x + v1.y*v2.y + v1.z*v2.z
                        logger.debug('vectorY no perpendicular '+str(vectorY))
                        vectorY.z = - vectorX.y*vectorY.y

                    # normalize vector
                    vectorY.normalize()

                vectorZ = vectorX ^ vectorY  # cross product
                vectorZ.normalize()
                # recalculate Y
                vectorY =vectorZ ^ vectorX
                vectorY.normalize()

                # get position
                position = curveDup.getPointAtParam(incrValue*(i-1), space='world')

                # apply matrix
                pm.xform(jointsList[-1], ws=True, m=[vectorX.x, vectorX.y, vectorX.z, 0,
                                            vectorY.x, vectorY.y, vectorY.z, 0,
                                            vectorZ.x, vectorZ.y, vectorZ.z, 0,
                                            position.x, position.y, position.z, 1])

                # freeze rotation
                pm.makeIdentity(jointsList[-1], apply=True, t=False, r=True, s=False, n=False, pn=False)

            # append new joint
            if i < joints:
                jointsList.append(joint)

        # construct hierarchy
        for i in range(joints-1):
            jointsList[i].addChild(jointsList[i+1])

        # delete duplicated curve
        pm.delete(curveDup.getTransform())

    # if not curve arg
    elif length:
        # distance between joints
        distanceBetween = length / joints
        for i in range(joints):
            joint = pm.joint(p=[distanceBetween*i,0,0])
            # append to list
            jointsList.append(joint)
        pm.select(cl=True)  # clear selection, to avoid possible errors with more chains

    return jointsList


def curveToSurface(curve, width=5.0, steps=10):
    """
    Create a surface from a nurbsCurve, using a loft node.
    Use BBox to select one axis and move cvs of the curves
    :param curve(pm or str): curve to generate loft
    :return(tranform node): loft surface between curves
    """
    # check types
    if isinstance(curve, str):
        curve = pm.PyNode(curve)
    if isinstance(curve, pm.nodetypes.Transform):
        curve = curve.getShape()

    curveTransform = curve.getTransform()

    # detect thinnest side using a bbox
    bbox = curve.boundingBox()
    bboxDict={}
    for i, axis in enumerate('xyz'):  # priority to z axis
        bboxDict[axis] = abs(bbox[0][i] - bbox[1][i])

    minVal = min(bboxDict.values())
    minAxis = bboxDict.keys()[bboxDict.values().index(minVal)]

    for axis in 'xz':
        if minAxis == 'y' and minVal == bboxDict[axis]:
            minAxis = axis

    # duplicate curve
    dupCurve1 = curveTransform.duplicate()[0]
    dupCurve1 = dupCurve1.getShape()
    dupCurve2 = curveTransform.duplicate()[0]
    dupCurve2 = dupCurve2.getShape()

    # edit points
    newPoint = pm.datatypes.Point(0, 0, 0)
    setattr(newPoint, minAxis, width / 2.0)
    print newPoint
    # edit cvPoints
    for j, curv in enumerate([dupCurve1, dupCurve2]):
        # rebuildCurve
        pm.rebuildCurve(curv,ch=False, rpo=True, rt=False, end=True, kr=False, kep=True, kt=False, s=steps, d=2, tol=0.01)
        sign = -1 if j%2 else 1  # increment positive or negative
        for i, CvPoint in enumerate(curv.getCVs('object')):
            curv.setCV(i, CvPoint + (newPoint*sign), 'object')
            curv.updateCurve()

    # create loft
    loft = pm.loft(dupCurve1, dupCurve2, ch=False, u=True, c=False, ar=True, d=2, ss=True,
                   rn=False, po=False, rsn=True)[0]
    pm.delete(dupCurve1.getTransform(), dupCurve2.getTransform())

    return loft


def variableFk(curve, numJoints, numControllers=3):
    """
    Create a variableFk system
    :param curve:
    :param numJoints:
    :return:
    """
    # check data type
    if isinstance(curve, str):
        curve = pm.PyNode(curve)
    if isinstance(curve, pm.nodetypes.Transform):
        curve = curve.getShape()

    systemGrp=pm.group(empty=True, name='variableFk_grp')

    # container of the controllers and surface
    controllerGrp=pm.group(empty=True, name='variableFk_ctr_grp')
    controllerGrp.inheritsTransform.set(False)
    systemGrp.addChild(controllerGrp)

    # create joint chain
    joints = jointChain(None, numJoints, curve)
    # duplicate joints, ctr joints, their will drive the surface skin
    jointsSkin = jointChain(None, numJoints, curve)
    systemGrp.addChild(jointsSkin[0])
    createRoots(jointsSkin)

    # create nurbs surface from curve
    surface = curveToSurface(curve, 2.5, numJoints)
    surfaceShape = surface.getShape()

    controllerGrp.addChild(surface)

    # connect joints and surface by skinCluster
    skinCluster = pm.skinCluster(jointsSkin, surfaceShape, mi=1)

    # create controller
    controllerList=[]
    jointsRoots = []
    for i in range(numControllers):
        # normal x axis
        controller = pm.circle(nr=(1,0,0), r=4.0, ch=False, name='variableFk%s_ctr' %i)[0]
        # copy rotation from joint
        pm.xform(controller, ws=True, m=pm.xform(jointsSkin[0], q=True, ws=True, m=True))
        controller.setRotation(jointsSkin[0].getRotation('world'), 'world')
        # create fallof attr
        pm.addAttr(controller, ln='fallof', sn='fallof', minValue=0.01, type='float',
                   defaultValue=0.2, maxValue=1.0, k=True)

        # create a root on each joint for controller, each controller will be connected on one root
        jointsRoots.append(createRoots(jointsSkin, str(controller)+'_auto'))

        controllerList.append(controller)
        controllerGrp.addChild(controller)

    # root controller
    controllerRoots = createRoots(controllerList)

    # snap root to surface
    for i, root in enumerate(controllerRoots):
        pointOnSurf = pm.createNode('pointOnSurfaceInfo')
        pointOnSurf.parameterV.set(0.5)
        surfaceShape.worldSpace[0].connect(pointOnSurf.inputSurface)

        # construct two transform matrix with fourByFourMatrix
        matrixNurbs = pm.createNode('fourByFourMatrix')
        matrixNurbIni = pm.createNode('fourByFourMatrix')  # with this we calculate the offset
        for n, attr in enumerate(['normalizedTangentU', 'normalizedNormal', 'normalizedTangentV', 'position']):
            for j, axis in enumerate('XYZ'):
                pointOnSurf.attr('%s%s'%(attr, axis)).connect(matrixNurbs.attr('in%s%s' %(n,j)))
                if n<3:
                    # store matrix info
                    matrixNurbIni.attr('in%s%s' %(n,j)).set(pointOnSurf.attr('%s%s'%(attr, axis)).get())

        # store initial root matrix
        rootMatrix = pm.xform(root, ws=True, q=True, m=True)
        rootMatrixNode = pm.createNode('fourByFourMatrix')
        for n, val in enumerate(rootMatrix):
            rowPos = n % 4
            colPos = n // 4
            if colPos==3 and rowPos < 3:
                val=0
            elif colPos==3 and rowPos==3:
                val=1
            else:
                val = val
            rootMatrixNode.attr('in%s%s' % (colPos, rowPos)).set(val)

        # calcOffset
        inverseNode = pm.createNode('inverseMatrix')
        rootMatrixNode.output.connect(inverseNode.inputMatrix)
        offsetNode = pm.createNode('multMatrix')
        matrixNurbIni.output.connect(offsetNode.matrixIn[0])
        inverseNode.outputMatrix.connect(offsetNode.matrixIn[1])

        # use mult matrix to add the offset
        multMatrix = pm.createNode('multMatrix')
        offsetNode.matrixSum.connect(multMatrix.matrixIn[0])
        matrixNurbs.output.connect(multMatrix.matrixIn[1])

        # now we need to read the matrix
        decompose = pm.createNode('decomposeMatrix')
        multMatrix.matrixSum.connect(decompose.inputMatrix)
        # and connect to the root controller
        decompose.outputTranslate.connect(root.translate)
        decompose.outputRotate.connect(root.rotate)

        # add slide attr to controller
        defaultSlide = (i+1) / (float(numControllers+1))
        pm.addAttr(controllerList[i], ln='slide', sn='slide', minValue=0.0, type='float', defaultValue=defaultSlide, maxValue=1.0, k=True)
        # connect to Uparamenter
        controllerList[i].slide.connect(pointOnSurf.parameterU)

    # TODO finish the method, connect rotation controller to joints. with fallof
    print jointsRoots
    for i, rootChain in enumerate(jointsRoots):
        print rootChain
        controller = controllerList[i]
        controllerRoot = controllerRoots[i]
        for j, rootJoint in enumerate(rootChain):
            print rootJoint
            # calculate the joint point
            jointPoint = j/(numJoints-1.0)  # range 0<->1 review
            rootJoint.rename('%s_jointOffset_%s' %(controllerRoot, jointPoint))

            # distance from controller
            distanceCtr = pm.createNode('plusMinusAverage')
            distanceCtr.operation.set(2)  # substract
            distanceCtr.input1D[0].set(jointPoint)
            controller.slide.connect(distanceCtr.input1D[1])
            ## absoluteValue ##
            square = pm.createNode('multiplyDivide')
            square.operation.set(3)  # power
            square.input2X.set(2)  # square
            distanceCtr.output1D.connect(square.input1X)
            # squareRoot
            squareRoot = pm.createNode('multiplyDivide')
            squareRoot.operation.set(3)  # power
            squareRoot.input2X.set(.5)  # square
            square.outputX.connect(squareRoot.input1X)

            ## compare with fallof ## f-(p-c)
            fallofDst = pm.createNode('plusMinusAverage')
            fallofDst.operation.set(2)  # subtract
            controller.fallof.connect(fallofDst.input1D[0])
            squareRoot.outputX.connect(fallofDst.input1D[1])
            # if the result < 0, stay in 0
            condition = pm.createNode('condition')
            condition.operation.set(2)  # greater than
            condition.secondTerm.set(0)
            condition.colorIfFalseR.set(0)
            fallofDst.output1D.connect(condition.firstTerm)
            fallofDst.output1D.connect(condition.colorIfTrueR)

            ## normalize the resutlt ##
            rotationMult = pm.createNode('multiplyDivide')
            rotationMult.operation.set(2)  # divide
            condition.outColorR.connect(rotationMult.input1X)
            controller.fallof.connect(rotationMult.input2X)

            ## connect to root joint ##
            rotationRoot = pm.createNode('multiplyDivide')
            rotationRoot.operation.set(1)  # multiply
            controller.rotate.connect(rotationRoot.input1)
            for axis in 'XYZ':
                rotationMult.outputX.connect(rotationRoot.attr('input2%s' % axis))
            # connect to to root
            rotationRoot.output.connect(rootJoint.rotate)

    # lock and hide attributes
    lockAndHideAttr(controllerList, True, False, True)

    # connect joints
    for i, joint in enumerate(joints):
        pm.orientConstraint(jointsSkin[i], joint, maintainOffset=False)
        pm.pointConstraint(jointsSkin[i], joint, maintainOffset=False)

