# file with creation funcs for akona
from maya import cmds
import pymel.core as pm
import re

import autoRig

def import_model(path='D:/_docs/_Animum/Akona/skinCluster/akona_skinPSD.ma'):
    cmds.file(new=True, force=True)
    cmds.file(path, i=True, force=True)
    # cmds.setAttr('akona_model_grp.visibility', True)


def akonaRigA(name='akona', path='D:\_docs\_Animum\Akona'):
    # spine Head
    reload(autoRig)  # review: delete
    akonaRig = autoRig.RigAuto(chName=name, path=path)  # create object
    # spine
    akonaRig.spine_auto('spine', lambda: akonaRig.addCluster('akona_chest_cluster', akonaRig.spineIKControllerList[-2], 'chest_cluster'),
                        lambda: akonaRig.addCluster('akona_belly_cluster', akonaRig.spineIKControllerList[1], 'belly_cluster'))
    # neckHead
    akonaRig.neckHead_auto()

    # legs
    akonaRig.ikFkChain_auto('left', akonaRig.ikControllers['spine'][0], 'leg', True, True,
                            lambda: akonaRig.foot_auto('left', ('leg', 'foot', 'toe'), 'zx'))
    akonaRig.ikFkChain_auto('right', akonaRig.ikControllers['spine'][0], 'leg', True, True,
                            lambda: akonaRig.foot_auto('right', ('leg', 'foot', 'toe'), 'zx'))

    # arms
    akonaRig.ikFkChain_auto('left', akonaRig.ikControllers['spine'][-1], 'arm', True, False,
                            lambda: akonaRig.hand_auto('left', ('arm', 'hand', 'finger'), None),
                            lambda: akonaRig.clavicle_auto('left', 'clavicle'),
                            lambda: akonaRig.ikFkChain_wire('akona_body_mesh', 'NONE'))

    akonaRig.ikFkChain_auto('right', akonaRig.ikControllers['spine'][-1], 'arm', True, False,
                            lambda: akonaRig.hand_auto('right', ('arm', 'hand', 'finger'), None),
                            lambda: akonaRig.clavicle_auto('right', 'clavicle'),
                            lambda: akonaRig.ikFkChain_wire('akona_body_mesh', 'NONE'))
