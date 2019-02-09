# file with creation funcs for akona
from maya import cmds
import pymel.core as pm
import re

import autoRig
reload(autoRig)  # review: delete

def import_model(path='D:/_docs/_Animum/Akona/skinCluster/akona_skinPSD_deformers.ma'):
    cmds.file(new=True, force=True)
    cmds.file(path, i=True, force=True)
    # cmds.setAttr('akona_model_grp.visibility', True)


def akonaRigA(name='akona', path='D:\_docs\_Animum\Akona'):
    # spine Head
    akonaRig = autoRig.RigAuto(chName=name, path=path)  # create object
    # spine
    akonaRig.spine_auto('spine', lambda: akonaRig.addCluster('akona_chest_cluster', akonaRig.spineIKControllerList[-2], 'chest_cluster'),
                        lambda: akonaRig.addCluster('akona_belly_cluster', akonaRig.spineIKControllerList[1], 'belly_cluster'))
    # neckHead
    akonaRig.neckHead_auto('neckHead', lambda: akonaRig.latticeBend_auto('akona_head_Lattice', akonaRig.neckHeadIKCtrList[-1]))

    sides = ['left', 'right']  # side types
    # legs
    for side in sides:
        akonaRig.ikFkChain_auto(side, akonaRig.ikControllers['spine'][0], 'leg', True, True,
                                lambda: akonaRig.foot_auto(('foot', 'toe'), 'zx'))
    """
    # arms
    for side in sides:
        akonaRig.ikFkChain_auto(side, akonaRig.ikControllers['spine'][-1], 'arm', True, False,
                                lambda: akonaRig.hand_auto(('hand', 'finger'), None),
                                lambda: akonaRig.clavicle_auto('clavicle'),  # cluster here for the costume
                                lambda: akonaRig.ikFkChain_wire('akona_body_mesh'))
    """
    ## skirt ##  # review: save main list too
    skirtDrivers = ['akona_leg_left_upperLeg_main_joint', 'akona_leg_right_upperLeg_main_joint']
    akonaRig.PSSkirt_auto('skirt', skirtDrivers, akonaRig.ikControllers['spine'][0], 0, 1.5, 80)

    return
    ## hair ##
    akonaRig.point_auto('hair', akonaRig.ikControllers['neckHead'][-1])
    ## clusters ##
    akonaRig.addCluster('akona_lapel_right_cluster', akonaRig.fkControllers['clavicle_right'], 'pole', .5)
    akonaRig.addCluster('akona_lapel_left_cluster', akonaRig.fkControllers['clavicle_left'], 'pole', .5)
    akonaRig.addCluster('akona_skirtLapel_right_cluster', 'akona_skirtO2_front_point_ctr', 'pole', .5)
    akonaRig.addCluster('akona_skirtLapel_left_cluster', 'akona_skirtB2_left_point_ctr', 'pole', .5)


    ## hide annoying things
    # list all joints of scene, and set its draw attribute to none
    hideElements = cmds.ls('%s*' % name, type='joint')
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
    cmds.sets(controllers, name='%s_ctr' % name)