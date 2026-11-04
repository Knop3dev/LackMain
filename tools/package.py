import argparse, hashlib, pathlib, platform, shutil, subprocess, sys, tarfile, zipfile
import importlib.metadata, sysconfig
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import VERSION

def run(args):
    subprocess.run(args, cwd=ROOT, check=True)

def build():
    target = platform.system().lower()
    arch = 'arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'x86_64'
    bundle = ROOT / 'dist' / f'lackminer-lbtc-{VERSION}-{target}-{arch}'
    bundle.mkdir(parents=True, exist_ok=True)
    for name in ['README.md', 'README.ru.md', 'LICENSE.txt', 'THIRD_PARTY.md']:
        shutil.copy2(ROOT / name, bundle / name)
    licenses = bundle / 'licenses'
    licenses.mkdir(exist_ok=True)
    for name in ['requests', 'urllib3', 'charset-normalizer', 'idna', 'certifi', 'ecdsa', 'six', 'cryptography', 'cffi', 'pycparser', 'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph', 'packaging']:
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        for file in distribution.files or []:
            if pathlib.PurePosixPath(str(file)).name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')):
                destination = licenses / name / pathlib.PurePosixPath(str(file)).name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(distribution.locate_file(file), destination)
    for directory in [pathlib.Path(sys.base_prefix), pathlib.Path(sysconfig.get_path('stdlib'))]:
        for name in ['LICENSE.txt', 'LICENSE']:
            if (directory / name).is_file():
                shutil.copy2(directory / name, licenses / 'Python-LICENSE.txt')
    for entry, name, window in [('main.py', 'lackminer-lbtc', False), ('gui_entry.py', 'lackminer-lbtc-gui', True)]:
        args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--name', name, '--add-data', 'sha256.cl:.', '--add-data', 'web:web', '--hidden-import', 'gui', '--hidden-import', 'miner', '--hidden-import', 'dashboard', '--hidden-import', 'adl']
        if window:
            args += ['--windowed']
        if target == 'windows':
            helper = ROOT / 'build/native/Release/lackminer-amd-control.exe'
            if not helper.exists():
                raise RuntimeError('Build the AMD helper first')
            args += ['--add-binary', str(helper) + ':.']
        args += [entry]
        run(args)
        exe = name + ('.exe' if target == 'windows' else '')
        shutil.copy2(ROOT / 'dist' / exe, bundle / exe)
        if target == 'darwin' and window and (ROOT / 'dist' / (name + '.app')).exists():
            shutil.copytree(ROOT / 'dist' / (name + '.app'), bundle / (name + '.app'), dirs_exist_ok=True)
    if target == 'windows':
        sdk = ROOT / 'build/native/_deps/adlx-src/ADLX SDK License Agreement.pdf'
        if not sdk.exists():
            raise RuntimeError('ADLX redistribution license is missing')
        shutil.copy2(sdk, bundle / 'AMD-ADLX-License.pdf')
    if target == 'linux':
        shutil.copytree(ROOT / 'hive', bundle / 'hive', dirs_exist_ok=True)
    archive = ROOT / 'dist' / (bundle.name + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in bundle.rglob('*'):
            if path.is_file():
                z.write(path, path.relative_to(bundle.parent))
    if target == 'linux':
        hive = ROOT / 'dist' / f'lackminer-lbtc-{VERSION}-hiveos.tar.gz'
        with tarfile.open(hive, 'w:gz') as t:
            t.add(bundle / 'lackminer-lbtc', arcname='lackminer-lbtc/lackminer-lbtc')
            for p in (ROOT / 'hive').iterdir():
                t.add(p, arcname='lackminer-lbtc/' + p.name)
            t.add(licenses, arcname='lackminer-lbtc/licenses')
            for n in ['README.md', 'README.ru.md', 'LICENSE.txt', 'THIRD_PARTY.md']:
                t.add(ROOT / n, arcname='lackminer-lbtc/' + n)
    for path in (ROOT / 'dist').glob('*.zip'):
        if path == archive:
            path.with_suffix('.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n')
    print(archive)
if __name__ == '__main__':
    build()
