import argparse, hashlib, pathlib, platform, shutil, subprocess, sys, tarfile, zipfile
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
    for name in ['README.md', 'README.ru.md', 'LICENSE.txt']:
        shutil.copy2(ROOT / name, bundle / name)
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
            for n in ['README.md', 'README.ru.md', 'LICENSE.txt']:
                t.add(ROOT / n, arcname='lackminer-lbtc/' + n)
    for path in (ROOT / 'dist').glob('*.zip'):
        if path == archive:
            path.with_suffix('.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n')
    print(archive)
if __name__ == '__main__':
    build()
