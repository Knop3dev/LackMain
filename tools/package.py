from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import zipfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--platform', choices=['windows', 'linux'], required=True)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--helper', type=Path)
parser.add_argument('--adlx-license', type=Path)
parser.add_argument('--cargo', default='cargo')
args = parser.parse_args()
version = '0.2.0'
output = root / 'dist'
output.mkdir(exist_ok=True)
stage = output / f'lackminer-qbtc-{version}-{args.platform}-x86_64'
if stage.exists():
    if stage.resolve().parent != output.resolve(): raise SystemExit('Invalid package staging path')
    shutil.rmtree(stage)
stage.mkdir(exist_ok=True)
shutil.copy2(args.binary, stage / ('lackminer-qbtc.exe' if args.platform == 'windows' else 'lackminer-qbtc'))
names = ['README.md', 'NOTICE'] + (['start-windows.cmd', 'start-windows.ps1'] if args.platform == 'windows' else ['start-linux.sh', 'node-linux.sh'])
for name in names:
    shutil.copy2(root / name, stage / name)
if args.helper:
    if not args.adlx_license or not args.adlx_license.is_file():
        raise SystemExit('ADLX license required when packaging the AMD helper')
    shutil.copy2(args.helper, stage / 'lackminer-gpu-control.exe')
metadata = json.loads(subprocess.check_output([args.cargo, 'metadata', '--locked', '--format-version', '1'], cwd=root))
licenses = stage / 'licenses'
licenses.mkdir(exist_ok=True)
report = []
for package in metadata['packages']:
    if package['name'] == 'lackminer-qbtc':
        continue
    folder = Path(package['manifest_path']).parent
    destination = licenses / f"{package['name']}-{package['version']}"
    candidates = [p for p in folder.iterdir() if p.is_file() and p.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'COPYRIGHT', 'NOTICE'))]
    if package.get('license_file'):
        candidates.append(folder / package['license_file'])
    for p in set(candidates):
        if p.is_file():
            destination.mkdir(exist_ok=True)
            shutil.copy2(p, destination / p.name)
    report.append({'name': package['name'], 'version': package['version'], 'license': package.get('license'), 'repository': package.get('repository')})
if args.adlx_license:
    shutil.copy2(args.adlx_license, licenses / 'ADLX SDK License Agreement.pdf')
(licenses / 'dependencies.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
archive = output / (stage.name + '.zip')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9, strict_timestamps=False) as z:
    for p in sorted(stage.rglob('*')):
        if p.is_file():
            info = zipfile.ZipInfo.from_file(p, str(p.relative_to(stage.parent)), strict_timestamps=False)
            if args.platform == 'linux':
                info.create_system = 3
                info.external_attr = (0o100755 if p.name == 'lackminer-qbtc' or p.suffix == '.sh' else 0o100644) << 16
            z.writestr(info, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
artifacts = [archive]
if args.platform == 'linux':
    hive = output / f'lackminer-qbtc-{version}-hiveos.tar.gz'
    with tarfile.open(hive, 'w:gz') as tar:
        for p in sorted(stage.rglob('*')):
            if p.is_file() and p.name != 'start-linux.sh':
                info = tar.gettarinfo(str(p), 'lackminer-qbtc/' + p.relative_to(stage).as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                if p.name == 'lackminer-qbtc' or p.suffix == '.sh': info.mode = 0o755
                with p.open('rb') as file: tar.addfile(info, file)
        for p in (root / 'hive').iterdir():
            info = tar.gettarinfo(str(p), 'lackminer-qbtc/' + p.name)
            info.mode = 0o755 if p.suffix == '.sh' else 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            with p.open('rb') as file: tar.addfile(info, file)
    artifacts.append(hive)
hashfile = output / f'SHA256SUMS-{args.platform}.txt'
hashfile.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in artifacts), encoding='ascii')
for p in artifacts: print(p)
