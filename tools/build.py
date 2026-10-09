import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
home=Path.home()
flags=os.environ.get('CARGO_ENCODED_RUSTFLAGS','').split('\x1f') if os.environ.get('CARGO_ENCODED_RUSTFLAGS') else os.environ.get('RUSTFLAGS','').split()
if os.name=='nt': flags+=['-C','target-feature=+crt-static']
for path,destination in [(home,'/build/home'),(root,'/build/source'),(Path(os.environ.get('CARGO_HOME',home/'.cargo')),'/build/cargo'),(Path(os.environ.get('RUSTUP_HOME',home/'.rustup')),'/build/rust')]:
    flags+=['--remap-path-prefix',str(path.resolve())+'='+destination]
env={**os.environ,'CARGO_ENCODED_RUSTFLAGS':'\x1f'.join(flags)}
raise SystemExit(subprocess.call(['cargo','build','--release','--locked',*sys.argv[1:]],cwd=root,env=env))
