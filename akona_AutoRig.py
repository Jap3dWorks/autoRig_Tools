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
                                lambda: akonaRig.foot_auto(('leg', 'foot', 'toe'), 'zx'))

    # arms
    for side in sides:
        akonaRig.ikFkChain_auto(side, akonaRig.ikControllers['spine'][-1], 'arm', True, False,
                                lambda: akonaRig.hand_auto(('arm', 'hand', 'finger'), None),
                                lambda: akonaRig.clavicle_auto('clavicle'),
                                lambda: akonaRig.ikFkChain_wire('akona_body_mesh'))