import os
import plistlib
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

NAME='收藏到英语卡片'
HERE=Path(__file__).resolve().parent
PYTHON='/Library/Frameworks/Python.framework/Versions/3.12/bin/python3'

def service_bundle(destination):
    contents=Path(destination)/'Contents'
    contents.mkdir(parents=True,exist_ok=True)
    command='exec '+PYTHON+' "$HOME/Library/Application Support/EnglishCards/program/collect.py"'
    action={
        'AMAccepts':{'Container':'List','Optional':False,'Types':['com.apple.cocoa.string']},
        'AMProvides':{'Container':'List','Types':['com.apple.cocoa.string']},
        'AMActionVersion':'2.0.3', 'AMParameterProperties':{k:{} for k in ['COMMAND_STRING','CheckedForUserDefaultShell','inputMethod','shell','source']},
        'AMRequiredResources':[],
        'ActionBundlePath':'/System/Library/Automator/Run Shell Script.action',
        'ActionName':'Run Shell Script',
        'ActionParameters':{'COMMAND_STRING':command,'CheckedForUserDefaultShell':True,'inputMethod':0,'shell':'/bin/zsh','source':''},
        'Application':['Automator'],'BundleIdentifier':'com.apple.RunShellScript','CFBundleVersion':'2.0.3',
        'CanShowSelectedItemsWhenRun':False,'CanShowWhenRun':True,'Category':['AMCategoryUtilities'],
        'Class Name':'RunShellScriptAction','InputUUID':str(uuid.uuid4()).upper(),
        'OutputUUID':str(uuid.uuid4()).upper(),'UUID':str(uuid.uuid4()).upper(),
        'Keywords':['Shell','Script','Run'], 'ShowWhenRun':False,'isViewVisible':True,
        'UnlocalizedApplications':['Automator'], 'arguments':{}
    }
    document={'AMApplicationBuild':'523','AMApplicationVersion':'2.10','AMDocumentVersion':'2',
        'actions':[{'action':action,'isViewVisible':True}],'connectors':{},
        'workflowMetaData':{'serviceInputTypeIdentifier':'com.apple.Automator.text',
            'serviceOutputTypeIdentifier':'com.apple.Automator.nothing','serviceProcessesInput':1,
            'serviceApplicationBundleID':'','serviceApplicationPath':'',
            'workflowTypeIdentifier':'com.apple.Automator.servicesMenu'}}
    info={'CFBundleIdentifier':'local.englishcards.capture','CFBundleName':NAME,
        'CFBundleShortVersionString':'2.0','CFBundleVersion':'2',
        'NSServices':[{'NSMenuItem':{'default':NAME},'NSMessage':'runWorkflowAsService',
            'NSSendTypes':['public.utf8-plain-text'],'NSRequiredContext':{}}]}
    for filename,value in [('Info.plist',info),('document.wflow',document)]:
        (contents/filename).write_bytes(plistlib.dumps(value,sort_keys=False))

def main():
    if not Path(PYTHON).exists(): raise RuntimeError('未找到此程序所需的 Python 3.12。')
    program=Path.home()/'Library/Application Support/EnglishCards/program'
    program.mkdir(parents=True,exist_ok=True)
    for name in ['app.py','core.py','translate.py','collect.py']:
        src,dest=HERE/name,program/name
        if src.resolve()!=dest.resolve():
            tmp=program/(name+'.new')
            shutil.copy2(src,tmp); os.replace(tmp,dest)
    target=Path.home()/'Library/Services'/(NAME+'.workflow')
    if target.exists():
        info=target/'Contents/Info.plist'
        if not info.exists() or plistlib.loads(info.read_bytes()).get('CFBundleIdentifier')!='local.englishcards.capture':
            raise RuntimeError('已有同名系统服务，安装已停止，原服务未更改。')
    service_bundle(target)
    # Refresh macOS' per-user Services registry; no global preferences changed.
    pbs=Path('/System/Library/CoreServices/pbs')
    if pbs.exists(): subprocess.run([str(pbs),'-update'],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print('安装完成。选中英文，右键 → 服务 → 收藏到英语卡片。')
    print('也可从顶部应用菜单 → 服务中找到它。若未出现，请退出并重新打开来源应用。')
    print('第一次启动新版时会导入旧收藏，请先退出旧版程序。')

if __name__=='__main__':
    if '--build-service' in sys.argv:
        service_bundle(HERE/(NAME+'.workflow'))
    else: main()
