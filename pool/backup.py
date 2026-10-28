import fcntl
from contextlib import closing
import json
import os
import pathlib
import shutil
import sqlite3
import tarfile
import tempfile
import time

def snapshot(destination):
    destination=pathlib.Path(destination);destination.mkdir(mode=0o700,parents=True,exist_ok=True)
    config=json.loads(pathlib.Path('/etc/lackpool/secrets/signer.json').read_text())
    with open(config['journal']+'.cycle.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix='.snapshot-',dir=destination) as temporary:
            root=pathlib.Path(temporary)
            for source,name in [(config['database'],'ledger.sqlite3'),(config['journal'],'journal.sqlite3')]:
                with closing(sqlite3.connect('file:'+source+'?mode=ro',uri=True)) as incoming,closing(sqlite3.connect(root/name)) as outgoing:
                    incoming.backup(outgoing)
                    if outgoing.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup integrity check failed')
            for source,name in [('/etc/lackpool/pool.json','pool.json'),('/etc/lackpool/secrets/signer.json','signer.json'),('/etc/lackpool/node.env','node.env'),('/etc/lackpool/rpc-proxy.json','rpc-proxy.json'),('/var/lib/lackpool/node/keystores/pool_payout.dat','pool_payout.dat')]:
                shutil.copyfile(source,root/name)
            stamp=time.strftime('%Y%m%d-%H%M%S',time.gmtime())
            target=destination/('lackpool-'+stamp+'.tar.gz');pending=target.with_suffix('.pending')
            descriptor=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'wb') as stream:
                with tarfile.open(fileobj=stream,mode='w:gz') as archive:
                    for source in root.iterdir():archive.add(source,arcname=source.name)
                    archive.add('/opt/lackpool/app',arcname='app',filter=lambda item:None if '__pycache__' in item.name else item)
                stream.flush();os.fsync(stream.fileno())
            pending.replace(target)
    with tarfile.open(target) as archive:
        expected={'ledger.sqlite3','journal.sqlite3','pool.json','signer.json','node.env','rpc-proxy.json','pool_payout.dat'}
        if not expected.issubset(archive.getnames()):raise ValueError('Backup is incomplete')
    for old in sorted(destination.glob('lackpool-*.tar.gz'),reverse=True)[48:]:old.unlink()
    print(json.dumps({'backup':target.name,'integrity':'ok','bytes':target.stat().st_size}))

if __name__=='__main__':snapshot('/var/backups/lackpool')
