import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

SOURCE=Path(__file__).resolve().parents[1]
MOCK_MINER='''#!/usr/bin/env python3
import fcntl,json,os,signal,sys,time
from pathlib import Path
root=Path.cwd()
args=sys.argv[1:]
if '--validate-address' in args: sys.exit(0)
if '--list-devices-json' in args:
 print((root/'inventory.json').read_text()); sys.exit(0)
def option(name): return args[args.index(name)+1]
watch='--chain-watch' in args
record={'pid':os.getpid(),'role':'watch' if watch else 'gpu'}
if not watch:
 record.update(device=int(option('--device')),lane=int(option('--nonce-lane')),lanes=int(option('--nonce-lanes')),base=option('--nonce-base'),wallet=option('--user'))
with (root/'events.jsonl').open('a') as file:
 fcntl.flock(file,fcntl.LOCK_EX)
 file.write(json.dumps(record)+'\\n'); file.flush()
 fcntl.flock(file,fcntl.LOCK_UN)
stop=False
def shutdown(*args):
 global stop
 stop=True
signal.signal(signal.SIGTERM,shutdown)
signal.signal(signal.SIGINT,shutdown)
while not stop:
 if not watch:
  device=record['device']
  data={'event':'stats','updated_at':int(time.time()),'hashrate':(device+1)*1000000,'accepted':device+1,'rejected':0,'stale':0,'controls':{'gpu':{'temperature':50+device,'fan_percent':40,'power':100}}}
  path=Path(option('--stats-file'))
  temp=path.with_suffix('.tmp')
  temp.write_text(json.dumps(data)); temp.replace(path)
 time.sleep(0.1)
'''

class HiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='lackminer-hive-')
        self.root=Path(self.temp.name)
        for p in (SOURCE/'hive').iterdir(): shutil.copy2(p,self.root/p.name)
        (self.root/'lackminer-qbtc').write_text(MOCK_MINER)
        (self.root/'lackminer-qbtc').chmod(0o755)
        (self.root/'node-linux.sh').write_text('#!/bin/bash\nif [[ ! -f node-started ]]; then touch node-started; echo node-start >>node-events; fi\n')
        inventory=[{'index':i,'name':'Fixture GPU '+str(i),'vendor':'Advanced Micro Devices, Inc.' if i%2==0 else 'NVIDIA Corporation','pci':f'0000:{i+1:02x}:00.0'} for i in range(15)]
        (self.root/'inventory.json').write_text(json.dumps(inventory))
        self.wallet='qbtc10y29nvfuwyxfxhkl4yqkenw4u6hshsk9zgaf5ctz4zfpa2gxe45qtwawce'
        self.env={**os.environ,'LACKMINER_ROOT':str(self.root),'CUSTOM_CONFIG_FILENAME':str(self.root/'miner.conf'),'CUSTOM_LOG_BASENAME':str(self.root/'logs'/'miner')}
        self.jq=os.environ.get('LACKMINER_TEST_JQ') or shutil.which('jq')
        if not self.jq: self.skipTest('jq required')
        self.env['LACKMINER_TEST_JQ']=self.jq
        self.process=None

    def tearDown(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid,signal.SIGKILL)
                self.process.wait()
        if self.process and self.process.stderr: self.process.stderr.close()
        self.temp.cleanup()

    def shell(self,command,*args,**kwargs):
        return subprocess.run(['bash','-c','jq(){ "$LACKMINER_TEST_JQ" "$@"; }; export -f jq; '+command,'fixture',*map(str,args)],env=self.env,text=True,capture_output=True,**kwargs)

    def start(self,extra=''):
        if self.process and self.process.stderr: self.process.stderr.close()
        (self.root/'miner.conf').write_text(self.wallet+'\n'+extra+'\n')
        self.process=subprocess.Popen(['bash','-c','jq(){ "$LACKMINER_TEST_JQ" "$@"; }; export -f jq; exec bash "$1"','fixture',str(self.root/'h-run.sh')],env=self.env,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)

    def events(self):
        p=self.root/'events.jsonl'
        if not p.exists(): return []
        import fcntl
        with p.open() as file:
            fcntl.flock(file,fcntl.LOCK_SH)
            lines=file.read().splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def await_condition(self,predicate,timeout=10):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate(): return
            if self.process and self.process.poll() is not None:
                self.fail('Supervisor stopped: '+self.process.stderr.read())
            time.sleep(0.1)
        self.fail('Supervisor condition timed out')

    def stats(self):
        result=self.shell('source "$1"; printf "%s\\n%s\\n" "$khs" "$stats"',self.root/'h-stats.sh',timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        khs,stats=result.stdout.strip().split('\n',1)
        return float(khs),json.loads(stats)

    def test_fifteen_gpus_shared_node_restart_and_cleanup(self):
        inventory=json.loads((self.root/'inventory.json').read_text())
        inventory.append({**inventory[0],'index':15})
        inventory.append({'index':16,'name':'Fixture integrated GPU','vendor':'Intel','pci':'0000:00:02.0'})
        (self.root/'inventory.json').write_text(json.dumps(inventory))
        self.start()
        self.await_condition(lambda:len([e for e in self.events() if e['role']=='gpu'])==15)
        self.await_condition(lambda:all((self.root/'_hive'/f'gpu-{i}.json').exists() for i in range(15)))
        events=self.events()
        self.assertEqual(len([e for e in events if e['role']=='watch']),1)
        cards=[e for e in events if e['role']=='gpu']
        self.assertEqual({e['lane'] for e in cards},set(range(15)))
        self.assertEqual({e['lanes'] for e in cards},{15})
        self.assertEqual(len({e['base'] for e in cards}),1)
        self.assertEqual({e['wallet'] for e in cards},{self.wallet})
        khs,stats=self.stats()
        self.assertEqual(khs,120000,stats)
        self.assertEqual(len(stats['hs']),15)
        self.assertEqual(stats['bus_numbers'],list(range(1,16)))
        failed=next(e for e in cards if e['device']==7)
        os.kill(failed['pid'],signal.SIGKILL)
        self.await_condition(lambda:len([e for e in self.events() if e.get('device')==7])==2,timeout=16)
        self.assertEqual(len([e for e in self.events() if e.get('device')==6]),1)
        self.assertEqual((self.root/'node-events').read_text().splitlines(),['node-start'])
        self.process.terminate(); self.process.wait(timeout=12)
        for e in self.events():
            with self.assertRaises(ProcessLookupError): os.kill(e['pid'],0)

    def test_three_five_and_ten_gpu_selection(self):
        for count in [3,5,10]:
            before=len(self.events())
            self.start('--devices '+','.join(map(str,range(count))))
            self.await_condition(lambda:sum(e['role']=='gpu' for e in self.events()[before:])>=count)
            self.await_condition(lambda:all((self.root/'_hive'/f'gpu-{i}.json').exists() for i in range(count)))
            khs,stats=self.stats()
            self.assertEqual(len(stats['hs']),count)
            self.assertEqual(khs,sum(range(1,count+1))*1000)
            self.process.terminate(); self.process.wait(timeout=12)

    def test_invalid_duplicate_selection_stops_before_node(self):
        for selection in ['0,0','99']:
            self.start('--devices '+selection)
            self.assertNotEqual(self.process.wait(timeout=5),0)
            self.assertFalse((self.root/'node-started').exists())

    def test_stale_gpu_is_zero_without_hiding_other_cards(self):
        state=self.root/'_hive';state.mkdir()
        (state/'gpus.json').write_text(json.dumps([{'index':0,'bus':1},{'index':1,'bus':2}]))
        (state/'started_at').write_text(str(int(time.time())-20))
        for index,timestamp in [(0,int(time.time())),(1,0)]:
            (state/f'gpu-{index}.json').write_text(json.dumps({'event':'stats','updated_at':timestamp,'hashrate':1000000,'accepted':2,'controls':{'gpu':{'temperature':60}}}))
        khs,stats=self.stats()
        self.assertEqual(khs,1000)
        self.assertEqual(stats['hs'],[1000000,0])
        self.assertEqual(stats['temp'],[60,None])
        self.assertEqual(stats['ar'],[4,0])

if __name__=='__main__': unittest.main()
