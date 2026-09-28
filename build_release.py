"""Build standalone and portable Windows releases with PyInstaller."""
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT=Path(__file__).resolve().parent
RELEASE=ROOT/'release'
BUILD=ROOT/'build'
NAME='归序'
VERSION='1.0.0'


def bundle(mode):
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed',
             '--name',NAME,'--icon',str(ROOT/'assets'/'guixu.ico'),
             '--paths',str(ROOT/'vendor'),
             '--add-data',f'{ROOT/"assets"/"guixu-icon.png"}:assets',
             '--add-data',f'{ROOT/"vendor"/"tkinterdnd2"/"tkdnd"/"win-x64"}:tkinterdnd2/tkdnd/win-x64',
             '--add-data',f'{ROOT/"vendor"/"tkinterdnd2"/"tkdnd"/"win-x64-tcl9"}:tkinterdnd2/tkdnd/win-x64-tcl9',
             '--distpath',str(BUILD/mode/'dist'),
             '--workpath',str(BUILD/mode/'work'),
             '--specpath',str(BUILD/mode/'spec'),
             '--onefile' if mode=='single' else '--onedir',str(ROOT/'app.py')]
    subprocess.run(command,cwd=ROOT,check=True)
    return BUILD/mode/'dist'/NAME


def verify(executable,kind):
    report=BUILD/f'{kind}-smoke.json'
    report.unlink(missing_ok=True)
    subprocess.run([str(executable),'--self-test',str(report)],cwd=ROOT,check=True,timeout=120)
    data=json.loads(report.read_text(encoding='utf-8'))
    if not data.get('ok') or not data.get('logo') or not data.get('tkdnd'):
        raise RuntimeError(f'{kind} self-test failed: {data}')
    return data


def digest(path):
    hasher=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            hasher.update(block)
    return hasher.hexdigest()


def main():
    if sys.platform!='win32':
        raise SystemExit('请在 Windows x64 上构建。')
    RELEASE.mkdir(exist_ok=True)
    portable=RELEASE/(NAME+'-便携版')
    archive=RELEASE/(NAME+'-便携版.zip')
    setup=RELEASE/(NAME+'-Setup-v'+VERSION+'.exe')
    if any(path.exists() for path in (portable,archive,setup)):
        raise FileExistsError('发布目录已有同名成品；请先检查旧版本并手动移走，再重新构建。')
    compiler=BUILD/'tools'/'inno'/'ISCC.exe'
    if not compiler.is_file():
        raise FileNotFoundError('未找到 Inno Setup 编译器：'+str(compiler))
    folder=bundle('portable')
    portable_exe=folder/(NAME+'.exe')
    portable_check=verify(portable_exe,'portable')
    shutil.copytree(folder,portable)
    guide=(f'{NAME} v{VERSION}  Windows x64\n\n'
           '双击 归序.exe 即可运行，无需安装 Python。\n'
           '便携包请先完整解压，再运行文件夹内的 归序.exe。\n'
           '便携版的托管设置、待分类清单和撤销记录保存在同目录的「用户数据」文件夹。\n'
           '自动监视仅在软件运行期间生效。\n'
           '如从只读位置运行，请先把整个文件夹复制到可写位置。\n')
    (portable/'使用说明.txt').write_text(guide,encoding='utf-8')
    notices=portable/'第三方许可'
    notices.mkdir()
    license_files={
        'Python-LICENSE.txt':Path(sys.base_prefix)/'LICENSE.txt',
        'Pillow-LICENSE.txt':Path(sys.prefix)/'Lib'/'site-packages'/'pillow-12.3.0.dist-info'/'licenses'/'LICENSE',
        'tkinterdnd2-LICENSE.txt':ROOT/'vendor'/'tkinterdnd2-0.6.3.dist-info'/'licenses'/'LICENSE',
        'PyInstaller-COPYING.txt':Path(sys.prefix)/'Lib'/'site-packages'/'pyinstaller-6.22.3.dist-info'/'licenses'/'COPYING.txt',
    }
    for name,source in license_files.items():
        shutil.copy2(source,notices/name)
    compiled=subprocess.run([str(compiler),str(ROOT/'归序安装包.iss')],cwd=ROOT,
                            capture_output=True,text=True,encoding='utf-8',errors='replace')
    if compiled.returncode:
        raise RuntimeError('安装程序编译失败：\n'+compiled.stdout[-4000:]+compiled.stderr[-1000:])
    if not setup.is_file():
        raise RuntimeError('安装程序未生成。')
    (portable/'便携模式.flag').write_text('归序便携版：数据保存在同目录的「用户数据」文件夹。\n',encoding='utf-8')
    portable_check=verify(portable/(NAME+'.exe'),'portable')
    if not portable_check.get('portable'):
        raise RuntimeError('便携模式标记未生效。')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as stream:
        for path in sorted(portable.rglob('*')):
            if path.is_file():
                stream.write(path,path.relative_to(RELEASE))
    manifest={'version':VERSION,'platform':'Windows x64','self_tests':{'portable':portable_check},
              'files':{setup.name:digest(setup),archive.name:digest(archive)}}
    (RELEASE/'SHA256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (RELEASE/'发布说明.txt').write_text(
        f'{NAME} v{VERSION} · Windows x64\n\n'
        '安装版：双击「归序-Setup-v1.0.0.exe」，按向导安装。可从开始菜单启动或在系统设置中卸载。\n'
        '便携版：完整解压「归序-便携版.zip」，双击文件夹内的「归序.exe」。\n'
        '便携版数据保存在同目录的「用户数据」中；安装版数据保存在 %LOCALAPPDATA%\\GuiyiOrganizer。\n'
        '安装包离线安装，不需要另行下载 Python 或软件组件。\n'
        '当前发布文件未做数字签名，Windows 可能显示未知发布者提示。\n'
        '两个下载文件的 SHA-256 摘要见 SHA256.json。\n',encoding='utf-8')
    print(json.dumps({'release':str(RELEASE),'files':list(manifest['files']),'self_tests':manifest['self_tests']},ensure_ascii=False))


if __name__=='__main__':
    main()
