import pymel.core as pm
from maya import OpenMaya

## callback selection change singleton ##
def callbackPrint(attr):
    """
    SelectionChanged
    """
    selection = pm.ls(sl=True)
    print "selection changed", selection, attr

if not "mSelEventsSing" in globals():
    mSelEventsSing = []

if not "createCallbackTemplate" in globals():
    def createCallbackTemplate(func):
        global mSelEventsSing
        print "Defined createCallBack: ", mSelEventsSing
        mEvId = OpenMaya.MEventMessage.addEventCallback("SelectionChanged", func)
        mSelEventsSing.append(mEvId)

if not hasattr(createCallbackTemplate, "c"):
    createCallbackTemplate.c = 0
    createCallbackTemplate(lambda x: callbackPrint("script"))

# clean
OpenMaya.MMessage.removeCallback(mSelEventsSing[0])
del (mSelEventsSing)
del (createCallbackTemplate)


#pm.scriptNode(scriptType=2, beforeScript=codeToRun, name='myCoolScriptNode')
