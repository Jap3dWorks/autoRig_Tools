# file with creation funcs for akona
import maya.cmds as cmds
import pymel.core as pm
import re

import ARAutoRig
import ARCore

def import_model(path='D:/_docs/_Animum/Akona/skinCluster/akona_skinPSD_d_facial.ma'):
    cmds.file(new=True, force=True)
    cmds.file(path, i=True, force=True)
    # cmds.setAttr('akona_model_grp.visibility', True)


def akonaRigA_Body(name='akona', path='D:/_docs/_Animum/Akona'):
    # spine Head
    akonaRig = ARAutoRig.ARAutoRig_Body(chName=name, path=path)  # create object
    # spine
    akonaRig.spine_auto('spine', lambda: akonaRig.addCluster('chest_cluster', akonaRig._spineIKControllerList[-2], 'chest_cluster'),
                        lambda: akonaRig.addCluster('belly_cluster', akonaRig._spineIKControllerList[1], 'belly_cluster'))
    # neckHead
    akonaRig.neckHead_auto('neckHead', lambda: akonaRig.latticeBend_auto('head_Lattice', akonaRig.neckHeadIKCtrList[-1]))

    sides = ['left', 'right']  # side types
    # legs
    for side in sides:
        akonaRig.ikFkChain_auto(side, akonaRig.ikControllers['spine'][0], 'leg', True, True,
                                lambda: akonaRig.foot_auto(('foot', 'toe'), 'zx'))

    # arms

    for side in sides:
        akonaRig.ikFkChain_auto(side, akonaRig.ikControllers['spine'][-1], 'arm', True, False,
                                lambda: akonaRig.hand_auto(('hand', 'finger'), None),
                                lambda: akonaRig.clavicle_auto('clavicle'),  # cluster here for the costume
                                lambda: akonaRig.ikFkChain_wire('body_mesh'))

    ## skirt ##  # review: save main list too
    skirtDrivers = ['leg_left_upperLeg_main_joint', 'leg_right_upperLeg_main_joint']
    akonaRig.PSSkirt_auto('skirt', skirtDrivers, akonaRig.ikControllers['spine'][0])

    ## hair ##
    akonaRig.point_auto('hair', akonaRig.ikControllers['neckHead'][-1])
    ## clusters ##
    akonaRig.addCluster('lapel_right_cluster', akonaRig.fkControllers['clavicle_right'], 'pole', .5)
    akonaRig.addCluster('lapel_left_cluster', akonaRig.fkControllers['clavicle_left'], 'pole', .5)
    akonaRig.addCluster('skirtLapel_right_cluster', 'skirtO2_front_point_ctr', 'pole', .5)
    akonaRig.addCluster('skirtLapel_left_cluster', 'skirtB2_left_point_ctr', 'pole', .5)


def akonaRigA_Face(name='akona', path='D:/_docs/_Animum/Akona'):
    """
    Func runs the facial rig
    :param name:
    :param path:
    :return:
    """
    akonaRig = ARAutoRig.ARAutoRig_Face(chName=name, path=path)  # create object

    ## wire lips
    lipsDef=["face_lips_Upper", "face_lips_lower"]
    akonaRig.wires_auto(lipsDef[0] + "_def_wire", "facialRig_mesh", None, 0.3)
    akonaRig.wires_auto(lipsDef[1] + "_def_wire", "facialRig_mesh", None, 0.3)

    # TODO: make a method move controller, in the normal direction of the surface, distance equal to the inner controller
    for lip in lipsDef:
        value = akonaRig.controllers[lip]
        for val in value:
            valShape = val.getShape()
            shapeP = valShape.getCVs()
            for i in range(len(shapeP)):
                shapeP[i] += (0,0,0.5)
            valShape.setCVs(shapeP)

    # look for same position controllers
    for i in [0, -1]:
        parents=akonaRig.controllers[lipsDef[1]][i].getAllParents()[:2]
        akonaRig.controllers[lipsDef[0]][i].addChild(akonaRig.controllers[lipsDef[1]][i])
        akonaRig.controllers[lipsDef[1]][i].visibility.set(0)
        pm.delete(parents)

    ## wire eyeBrow
    browsZone = ["face_left_browIn", "face_right_browIn"]
    akonaRig.wires_auto(browsZone[0] + "_def_wire", "facialRig_mesh", None, 0.3)
    akonaRig.wires_auto(browsZone[1]+"_def_wire", "facialRig_mesh", None, 0.3)

    ## general face wire
    faceZone = "face_face"
    akonaRig.wires_auto(faceZone+"_def_wire", "facialRig_mesh", None, 15, "circle")
    # hide first and last
    pm.delete(akonaRig.controllers[faceZone][0].getShape())
    pm.delete(akonaRig.controllers[faceZone][-1].getShape())

    ## project deformers, to drive brows and lips from face wire
    for i in [lipsDef[0], lipsDef[1], browsZone[0], browsZone[1]]:
        ARCore.ARCore.DeformerOp.addToDeformer(faceZone+"_def_wire", akonaRig.sysObj[i])


def hideElements():
    """
    Hide annoying things like curves, ik handles, joints, etc
    :return:
    """
    ## hide annoying things
    # list all joints of scene, and set its draw attribute to none
    hideElements = cmds.ls(type='joint')
    for element in hideElements:
        cmds.setAttr('%s.drawStyle' % element, 2)
    # hide ik handles
    hideElements = cmds.ls(type='ikHandle')
    for element in hideElements:
        cmds.setAttr('%s.visibility' % element, False)
    # hide curves
    hideElements = cmds.ls(type='nurbsCurve')
    for element in hideElements:
        if not 'ctr' in element:
            cmds.setAttr('%s.visibility' % element, False)

    # ctr Sets
    controllers = cmds.ls('*_ctr')
    cmds.sets(controllers, name='controllers_set')


def main():
    import autoRig_Tools
    ## launch autoRig ##
    reload(autoRig_Tools)
    import_model("D:/_docs/_Animum/Akona/skinCluster/FacialJoints/akona_skin_facial41.ma")

    akonaRigA_Body()
    akonaRigA_Face()

    hideElements()

    return 0