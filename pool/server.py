import argparse
import asyncio
import collections
import copy
import hashlib
import json
import logging
import pathlib
import secrets
import time
import urllib.parse

from accounting import Ledger
from core import OWNER,SAT,address_hash,block_digest,header_bytes,public_block_to_full,roots,rpc

LOG=logging.getLogger('lackpool')

class Pool:
    def __init__(self,config):
        self.config=config
        self.ledger=Ledger(config['database'],config.get('fee_bps',150),config.get('min_payout_sats',10*SAT))
        self.owner=config.get('owner',OWNER);self.owner_hash=address_hash(self.owner)
        self.node=config['node'];self.public=config.get('public','https://explorer.qbtc-core.org')
        self.template=None;self.anchor=None;self.ready=False;self.reason='Node synchronizing'
        self.started=time.time();self.sessions={};self.jobs={};self.job_id=int(time.time()*1000)
        self.next_tag=1;self.last_public_check=0;self.last_job_time=0
        self.last_maturity_check=0;self.tx_roots=None
        self.rejected=collections.Counter();self.block_lock=asyncio.Lock()

    async def call(self,base,method,body=None):
        return await asyncio.to_thread(rpc,base,method,body)

    async def refresh(self):
        while True:
            try:
                local=await self.call(self.node,'get_info')
                public=await self.call(self.public,'get_info')
                local_height=local['current_height'];public_height=public['current_height']
                if local_height<public_height:
                    self.ready=False;self.reason=f'Node syncing: {local_height}/{public_height}'
                    for height in range(local_height+1,min(public_height,local_height+8)+1):
                        existing=await self.call(self.public,'get_block',{'height':height})
                        full=public_block_to_full(existing)
                        response=await self.call(self.node,'submit_block',{'block':full})
                        if not response.get('success'):raise ValueError('Node rejected public synchronization block')
                    await self.pause_all(self.reason)
                    await asyncio.sleep(.2);continue
                if local_height>public_height:
                    row=self.ledger.db.execute("SELECT node_response FROM blocks WHERE height=? AND state='pending' ORDER BY created DESC LIMIT 1",(public_height+1,)).fetchone()
                    if row:
                        candidate=json.loads(row['node_response']).get('block')
                        if candidate:await self.call(self.public,'submit_block',{'block':candidate})
                    raise ValueError('Waiting for public confirmation of local tip')
                template=await self.call(self.node,'get_block_template',{'miner_address':self.owner})
                if not template or template['current_height']!=public_height+1:
                    raise ValueError('Node template does not extend the current tip')
                canonical=await self.call(self.public,'get_block',{'height':public_height})
                if block_digest(canonical)!=template['previous_hash']:
                    raise ValueError('Local/public chain hashes differ')
                coinbase=template['transactions'][0]
                if any(bytes(o['public_key_hash'])!=self.owner_hash for o in coinbase['outputs']):
                    raise ValueError('Unexpected coinbase payout address')
                if coinbase['inputs']!=[{'previous_output_hash':[0]*32,'vout':template['current_height']}]:
                    raise ValueError('Unexpected coinbase input')
                reward=sum(output['value'] for output in coinbase['outputs'])
                marked=reward//3+self.config.get('coinbase_marker',61371)
                if not 0<marked<reward:raise ValueError('Reward is too small for pool identification')
                coinbase['outputs']=[{'value':reward-marked,'public_key_hash':list(self.owner_hash),'recovery':None},
                                     {'value':marked,'public_key_hash':list(self.owner_hash),'recovery':None}]
                changed=not self.ready or self.anchor!=template['previous_hash'] or self.template!=template
                if changed:self.tx_roots=roots(template['transactions'])
                self.template=template;self.anchor=template['previous_hash'];self.ready=True;self.reason=None
                self.last_public_check=time.monotonic()
                if changed or time.time()-self.last_job_time>=20:
                    self.last_job_time=time.time()
                    await asyncio.gather(*(self.notify(session) for session in list(self.sessions.values()) if session['address']),return_exceptions=True)
                for job_id,job in list(self.jobs.items()):
                    if time.time()-job['created']>180:self.jobs.pop(job_id,None)
                if time.time()-self.last_maturity_check>=30:
                    await self.mature(public_height);self.last_maturity_check=time.time()
            except Exception as error:
                self.ready=False;self.reason=str(error)[:180]
                await self.pause_all(self.reason)
                LOG.warning('Mining paused: %s',self.reason)
            await asyncio.sleep(2)

    async def mature(self,tip):
        pending=self.ledger.db.execute("SELECT hash,height,state FROM blocks WHERE state='pending' AND height<=? ORDER BY height LIMIT 12",(tip,)).fetchall()
        for block in pending:
            canonical=await self.call(self.public,'get_block',{'height':block['height']})
            self.ledger.observe(block['hash'],block_digest(canonical),tip)
        self.ledger.queue_payouts()

    async def send(self,session,message):
        async with session['write_lock']:
            session['writer'].write((json.dumps(message,separators=(',',':'))+'\n').encode())
            await asyncio.wait_for(session['writer'].drain(),10)

    async def pause_all(self,reason):
        await asyncio.gather(*(self.send(session,{'id':None,'method':'mining.pause','params':[reason]}) for session in list(self.sessions.values()) if session['address']),return_exceptions=True)

    async def notify(self,session):
        if not self.ready or not self.template:return
        template=self.template
        transactions=template['transactions']
        tx_root,witness_root=self.tx_roots
        header={'timestamp':max(int(time.time()),session.get('timestamp',0)),
                'previous_hash':list(bytes.fromhex(template['previous_hash'])),
                'merkle_root':list(tx_root),'commit_merkle_root':list(witness_root),
                'nonce':0,'target':template['target']}
        session['timestamp']=header['timestamp']
        self.job_id+=1;job_id=self.job_id
        target=max(template['target'],session.get('share_target',self.config.get('share_target',(1<<31)-1)))
        low=session['tag']<<48;high=(session['tag']+1)<<48
        self.jobs[job_id]={'block':{'header':header,'transactions':transactions},'height':template['current_height'],
                           'target':target,'address':session['address'],'tag':session['tag'],'created':time.time()}
        session.setdefault('jobs',collections.deque()).append(job_id)
        while len(session['jobs'])>6:self.jobs.pop(session['jobs'].popleft(),None)
        await self.send(session,{'id':None,'method':'mining.notify','params':[job_id,template['previous_hash'],tx_root.hex(),witness_root.hex(),header['timestamp'],template['target'],target,low,high]})

    async def submit(self,session,params):
        if not session['address']:raise ValueError('Authorize first')
        if len(params)!=3:raise ValueError('Expected worker, job ID and nonce')
        job_id,nonce=params[1:]
        if type(job_id) is not int or type(nonce) is not int or not 0<=nonce<(1<<64):raise ValueError('Invalid job or nonce')
        job=self.jobs.get(job_id)
        if not job or job['address']!=session['address'] or job['tag']!=session['tag']:raise ValueError('Unknown job')
        if not self.ready or time.monotonic()-self.last_public_check>12:raise ValueError('Chain synchronization paused')
        if bytes(job['block']['header']['previous_hash']).hex()!=self.anchor:raise ValueError('Stale job')
        if not (session['tag']<<48)<=nonce<((session['tag']+1)<<48):raise ValueError('Nonce outside assigned range')
        block=copy.deepcopy(job['block']);block['header']['nonce']=nonce
        digest=block_digest(block);hash_num=int(digest[:16],16)
        if hash_num>job['target']:raise ValueError('Low difficulty share')
        share_id=self.ledger.share(digest,session['address'],session['worker'],job_id,nonce,job['target'])
        if share_id is None:raise ValueError('Duplicate share')
        session['accepted']+=1;session['last_share']=time.time()
        if hash_num<=block['header']['target']:
            async with self.block_lock:
                self.ready=False;self.reason='Checking found block in the public chain'
                reward=sum(output['value'] for output in block['transactions'][0]['outputs'])
                self.ledger.found(digest,job['height'],reward,{'state':'submitting','block':block})
                await self.pause_all(self.reason)
                try:receipt=await self.call(self.node,'submit_block',{'block':block})
                except Exception:
                    LOG.warning('Block submission outcome pending; candidate saved for reconciliation')
                    return True
                if receipt.get('success'):
                    self.ledger.db.execute('UPDATE blocks SET node_response=? WHERE hash=?',(json.dumps({'receipt':receipt,'block':block}),digest))
                    LOG.info('BLOCK accepted by node height=%s hash=%s',job['height'],digest)
                    try:await self.call(self.public,'submit_block',{'block':block})
                    except Exception:LOG.warning('Public block relay pending')
                else:
                    current=await self.call(self.node,'get_block',{'height':job['height']})
                    if not current or block_digest(current)!=digest:self.ledger.observe(digest,'not-canonical',job['height'])
                    LOG.warning('Network candidate not accepted: %s',receipt.get('message','unknown'))
        return True

    async def miner(self,reader,writer):
        peer=writer.get_extra_info('peername');ip=peer[0]
        if len(self.sessions)>=1024 or sum(s['ip']==ip for s in self.sessions.values())>=64:
            writer.close();return
        used={s['tag'] for s in self.sessions.values()}
        while self.next_tag in used:self.next_tag=self.next_tag%65534+1
        tag=self.next_tag;self.next_tag=self.next_tag%65534+1
        session={'writer':writer,'write_lock':asyncio.Lock(),'address':None,'worker':'','tag':tag,
                 'ip':ip,'accepted':0,'last_share':None,'connected':time.time()}
        self.sessions[tag]=session
        limiter=collections.deque()
        try:
            while True:
                line=await asyncio.wait_for(reader.readline(),600 if session['address'] else 30)
                if not line:break
                if len(line)>8192:break
                request=json.loads(line)
                now=time.monotonic()
                while limiter and now-limiter[0]>1:limiter.popleft()
                if len(limiter)>=100:break
                limiter.append(now)
                if not isinstance(request,dict):raise ValueError('Expected a JSON-RPC object')
                request_id=request.get('id');method=request.get('method');params=request.get('params',[])
                try:
                    if method=='mining.subscribe':
                        if len(params)>1 and isinstance(params[1],dict) and params[1].get('device')=='cpu':
                            session['share_target']=(1<<40)-1
                        result={'protocol':'lackpool/1','pool':'LackPool','fee_percent':1.5,'payout':'PROP','minimum_payout_qbtc':10,'payout_address':self.owner}
                    elif method=='mining.authorize':
                        if not params or not isinstance(params[0],str) or len(params[0])>160:raise ValueError('Invalid worker')
                        address,_,worker=params[0].partition('.')
                        address_hash(address)
                        if not all(c.isalnum() or c in '-_' for c in worker):raise ValueError('Invalid worker name')
                        if session['address']:raise ValueError('Already authorized')
                        session['address']=address;session['worker']=worker or 'default';result=True
                    elif method=='mining.submit':
                        result=await self.submit(session,params)
                    else:raise ValueError('Unsupported Stratum method')
                    await self.send(session,{'id':request_id,'result':result,'error':None})
                    if method=='mining.authorize':
                        if self.ready:await self.notify(session)
                        else:await self.send(session,{'id':None,'method':'mining.pause','params':[self.reason]})
                except ValueError as error:
                    self.rejected[str(error)]+=1
                    await self.send(session,{'id':request_id,'result':False,'error':[20,str(error),None]})
        except (OSError,ValueError,asyncio.TimeoutError,asyncio.LimitOverrunError):
            pass
        except Exception:
            LOG.exception('Miner session failed')
        finally:
            self.sessions.pop(tag,None);writer.close()
            try:await writer.wait_closed()
            except OSError:pass

    def stats(self,address=None):
        now=time.time();window=600
        work=self.ledger.db.execute('SELECT COALESCE(SUM(work),0),COUNT(*) FROM shares WHERE created>=?',(now-600,)).fetchone()
        value=self.ledger.summary(address)
        value.update({'name':'LackPool Q-BTC','algorithm':'SHA-256 / Q-BTC 120-byte header','payout_scheme':'PROP',
                      'mining_address':self.owner,'stratum':'stratum+tcp://ashenward.ru:3334',
                      'state':'mining' if self.ready else 'syncing','reason':self.reason,
                      'height':self.template['current_height']-1 if self.template else None,
                      'active_miners':len([s for s in self.sessions.values() if s['address']]),
                      'hashrate_estimate':work[0]/window,'hashrate_method':'accepted-share work over a rolling 10-minute window',
                      'accepted_shares_10m':work[1],'rejected_shares':sum(self.rejected.values()),
                      'payout_signer':self.signer_status(),'updated_at':int(now)})
        if address:
            individual=self.ledger.db.execute('SELECT COALESCE(SUM(work),0),COUNT(*) FROM shares WHERE address=? AND created>=?',(address,now-600)).fetchone()
            value.update(address=address,miner_hashrate_estimate=individual[0]/window,miner_shares_10m=individual[1],
                         workers=[{'name':s['worker'],'accepted':s['accepted'],'last_share':s['last_share']} for s in self.sessions.values() if s['address']==address])
        else:
            value['miners']=[dict(row) for row in self.ledger.db.execute('SELECT address,COUNT(*) shares,COALESCE(SUM(work),0) work FROM shares WHERE created>=? GROUP BY address ORDER BY work DESC LIMIT 100',(now-600,))]
        return value

    def signer_status(self):
        try:
            path=pathlib.Path(self.config['signer_status'])
            if time.time()-path.stat().st_mtime>180:return {'state':'offline'}
            return json.loads(path.read_text())
        except (OSError,ValueError,KeyError):return {'state':'not_configured'}

    async def http(self,reader,writer):
        try:
            head=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),5)
            if len(head)>16384:raise ValueError('Headers too large')
            lines=head.decode('ascii').split('\r\n');method,path,_=lines[0].split(' ',2)
            if method!='GET':raise ValueError('Only GET is supported')
            route=urllib.parse.urlsplit(path).path
            status='200 OK';content_type='application/json; charset=utf-8'
            if route=='/api/stats':body=json.dumps(self.stats(),separators=(',',':')).encode()
            elif route.startswith('/api/miner/'):
                address=urllib.parse.unquote(route[len('/api/miner/'):]);address_hash(address)
                body=json.dumps(self.stats(address),separators=(',',':')).encode()
            elif route in ('/','/index.html','/app.js','/style.css'):
                name='index.html' if route=='/' else route[1:]
                body=(pathlib.Path(__file__).parent/'web'/name).read_bytes()
                content_type={'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[name]
            else:status='404 Not Found';body=b'{"error":"Not found"}'
            writer.write(f'HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {len(body)}\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\nConnection: close\r\n\r\n'.encode()+body)
            await writer.drain()
        except Exception:
            pass
        finally:writer.close()

async def main(config):
    pool=Pool(config)
    stratum=await asyncio.start_server(pool.miner,config.get('stratum_host','0.0.0.0'),config.get('stratum_port',3334),limit=8193)
    http=await asyncio.start_server(pool.http,'127.0.0.1',config.get('http_port',3335),limit=16385)
    LOG.info('Stratum online; fee 1.5%%; PROP; payout threshold 10 QBTC')
    async with stratum,http:
        await asyncio.gather(stratum.serve_forever(),http.serve_forever(),pool.refresh())

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    args=parser.parse_args();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    asyncio.run(main(json.loads(pathlib.Path(args.config).read_text())))
