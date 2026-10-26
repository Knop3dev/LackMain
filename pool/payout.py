import argparse
import hashlib
import json
import pathlib
import sqlite3
import time

from accounting import Ledger
from core import SAT,address_hash,block_digest,merkle,rpc,transaction_bytes

def verify_reward(block,expected_hash,expected_height,expected_reward,owner,marker=61371):
    digest=block_digest(block)
    if digest!=expected_hash or block['height']!=expected_height:
        raise ValueError('Canonical block identity differs from the pool record')
    if int(digest[:16],16)>block['target']:raise ValueError('Invalid reward PoW')
    tx=block['transactions'][0];reward=sum(item['value_sats'] for item in tx['outputs'])
    if reward!=expected_reward or len(tx['outputs'])!=2:raise ValueError('Pool coinbase marker missing')
    marked=reward//3+marker;key=address_hash(owner)
    if [item['value_sats'] for item in tx['outputs']]!=[reward-marked,marked]:raise ValueError('Not a pool reward')
    if any(item['address_hash']!=key.hex() for item in tx['outputs']):raise ValueError('Reward belongs to another wallet')
    if tx['inputs']!=[{'prev_txid':'0'*64,'vout':expected_height}]:raise ValueError('Invalid pool coinbase')
    encoded={'inputs':[{'previous_output_hash':[0]*32,'vout':expected_height}],
             'outputs':[{'value':item['value_sats'],'public_key_hash':list(key),'recovery':None} for item in tx['outputs']], 'witnesses':[]}
    if hashlib.sha256(transaction_bytes(encoded)).hexdigest()!=tx['txid']:raise ValueError('Invalid reward transaction ID')
    if merkle([bytes.fromhex(item['txid']) for item in block['transactions']]).hex()!=block['merkle_root']:
        raise ValueError('Reward is not committed in this block')
    return reward

class Signer:
    def __init__(self,config):
        self.config=config;self.owner=config['owner'];address_hash(self.owner)
        self.ledger=Ledger(config['database'])
        self.db=sqlite3.connect(config['journal'],isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
CREATE TABLE IF NOT EXISTS verified(hash TEXT PRIMARY KEY,height INTEGER,reward INTEGER,fee INTEGER,allocations TEXT);
CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,address TEXT,amount INTEGER,fee_reserve INTEGER,state TEXT,txid TEXT UNIQUE,sent_height INTEGER,next_height INTEGER,confirmed_height INTEGER,actual_fee INTEGER);
''')

    def local(self,method,body=None):
        return rpc(self.config['node'],method,body,self.config['rpc_token'],timeout=30)

    def public(self,method,body=None):return rpc(self.config['public'],method,body,timeout=12)

    def status(self,state,reason=None):
        path=pathlib.Path(self.config['status_file']);temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'state':state,'reason':reason,'updated_at':int(time.time())}))
        temporary.replace(path)

    def verify_chain(self):
        local=self.local('get_info')['current_height'];tip=self.public('get_info')['current_height']
        if local!=tip:raise ValueError('Payouts paused: local/public tips differ')
        anchor=self.db.execute('SELECT hash,height FROM verified ORDER BY height DESC LIMIT 1').fetchone()
        if anchor:
            for endpoint in (self.local,self.public):
                if block_digest(endpoint('get_block',{'height':anchor['height']}))!=anchor['hash']:
                    raise ValueError('Previously matured pool rewards were reorganized; manual review required')
        rows=self.ledger.db.execute("SELECT * FROM blocks WHERE height>=? AND height<=? AND state IN ('pending','matured') ORDER BY height",(self.config['activation_height'],tip-100)).fetchall()
        for block in rows:
            if self.db.execute('SELECT 1 FROM verified WHERE hash=?',(block['hash'],)).fetchone():continue
            public=self.public('get_block',{'height':block['height']})
            canonical=block_digest(public)
            if canonical!=block['hash']:
                self.ledger.observe(block['hash'],canonical,tip);continue
            verify_reward(public,block['hash'],block['height'],block['reward'],self.owner,self.config.get('coinbase_marker',61371))
            if block_digest(self.local('get_block',{'height':block['height']}))!=canonical:
                raise ValueError('Reward block differs between nodes')
            allocations=json.loads(block['allocations']);fee=block['reward']*150//10000
            if block['fee']!=fee or sum(allocations.values())!=block['reward']-fee:
                raise ValueError('Reward accounting does not balance')
            for address,amount in allocations.items():
                address_hash(address)
                if type(amount) is not int or amount<0:raise ValueError('Invalid allocation')
            self.db.execute('INSERT INTO verified VALUES (?,?,?,?,?)',(canonical,block['height'],block['reward'],fee,json.dumps(allocations,sort_keys=True)))
            self.ledger.observe(canonical,canonical,tip)
        return tip

    def reconcile(self,tip):
        for receipt in self.db.execute("SELECT * FROM receipts WHERE state IN ('broadcast','confirmed','retained')").fetchall():
            if receipt['state']=='retained':
                self.ledger.db.execute("UPDATE payouts SET state='retained',updated=? WHERE id=?",(time.time(),receipt['id']));continue
            if receipt['state']=='confirmed':
                if receipt['confirmed_height'] is not None and tip<receipt['confirmed_height']+100:
                    canonical=self.public('get_block',{'height':receipt['confirmed_height']})
                    if not any(tx['txid']==receipt['txid'] for tx in canonical['transactions']):
                        raise ValueError('Confirmed payout was reorganized; automatic resend is disabled')
                row=self.ledger.db.execute('SELECT state,address,amount FROM payouts WHERE id=?',(receipt['id'],)).fetchone()
                if row and (row['address']!=receipt['address'] or row['amount']!=receipt['amount']):raise ValueError('Payout record changed after signing')
                if row and row['state']!='confirmed':
                    self.ledger.db.execute('BEGIN IMMEDIATE')
                    try:
                        self.ledger.db.execute("UPDATE payouts SET state='confirmed',txid=?,updated=? WHERE id=?",(receipt['txid'],time.time(),receipt['id']))
                        self.ledger.db.execute('UPDATE balances SET paid=paid+? WHERE address=?',(receipt['amount'],receipt['address']))
                        self.ledger.db.execute('COMMIT')
                    except Exception:self.ledger.db.execute('ROLLBACK');raise
                continue
            self.ledger.submitted(receipt['id'],receipt['txid'])
            found_height=receipt['confirmed_height']
            if found_height is None:
                first=receipt['next_height'];last=min(tip,first+31)
                for height in range(first,last+1):
                    block=self.local('get_block',{'height':height})
                    tx=next((tx for tx in block.get('transactions',[]) if tx['txid']==receipt['txid']),None)
                    if tx:
                        found_height=height
                        actual_fee=(30+5350*len(tx['inputs'])+2*50)*25
                        if actual_fee>receipt['fee_reserve']:raise ValueError('Transaction fee exceeded the reserved upper bound')
                        self.db.execute('UPDATE receipts SET confirmed_height=?,actual_fee=? WHERE id=?',(height,actual_fee,receipt['id']));break
                if found_height is None:self.db.execute('UPDATE receipts SET next_height=? WHERE id=?',(last+1,receipt['id']))
            if found_height is not None and tip>=found_height+5:
                block=self.public('get_block',{'height':found_height})
                if not any(tx['txid']==receipt['txid'] for tx in block['transactions']):
                    raise ValueError('Payout transaction was reorganized; do not send it again')
                self.db.execute("UPDATE receipts SET state='confirmed' WHERE id=?",(receipt['id'],))

    def cycle(self):
        if self.db.execute("SELECT 1 FROM receipts WHERE state IN ('intent','unknown')").fetchone():
            raise ValueError('A transfer outcome is unknown; automatic retries are disabled')
        tip=self.verify_chain();self.reconcile(tip)
        unlocked=self.local('wallet_unlock',{'wallet_name':self.config['wallet_name'],'password':self.config['password']})
        if not unlocked.get('success') or unlocked.get('address')!=self.owner:raise ValueError('Payout wallet authentication failed')
        credits={}
        fee_budget=0
        for row in self.db.execute('SELECT allocations,fee FROM verified'):
            fee_budget+=row['fee']
            for address,amount in json.loads(row['allocations']).items():credits[address]=credits.get(address,0)+amount
        used={}
        for row in self.db.execute('SELECT address,amount,fee_reserve,actual_fee,state FROM receipts'):
            used[row['address']]=used.get(row['address'],0)+row['amount']
            fee_budget-=row['actual_fee'] if row['actual_fee'] is not None else row['fee_reserve']
        self.ledger.queue_payouts()
        row=self.ledger.db.execute("SELECT * FROM payouts WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
        if not row:self.status('ready');return
        address_hash(row['address'])
        if row['amount']<10*SAT or row['amount']>credits.get(row['address'],0)-used.get(row['address'],0):
            raise ValueError('Payout exceeds independently verified matured earnings')
        balance=self.local('get_balance',{'address':self.owner})
        reserve=0 if row['address']==self.owner else balance['max_send_fee_sats']
        if reserve>fee_budget or balance['max_send_sats']<row['amount']:
            self.status('ready','Waiting for sufficient spendable funds or fee reserve');return
        if row['address']!=self.owner and balance['confirmed_sats']+balance['locked_sats']+balance['pending_sats']-row['amount']-reserve<self.config['protected_balance_sats']:
            self.status('ready','Protected pre-pool balance would be touched; payment deferred');return
        claimed=self.ledger.claim()
        if not claimed or claimed['id']!=row['id']:raise ValueError('Payout claim changed')
        self.db.execute('INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?)',(row['id'],row['address'],row['amount'],reserve,'intent',None,tip,tip,None,None))
        if row['address']==self.owner:
            self.db.execute("UPDATE receipts SET state='retained',actual_fee=0 WHERE id=?",(row['id'],))
            self.ledger.db.execute("UPDATE payouts SET state='retained',updated=? WHERE id=?",(time.time(),row['id']));self.status('ready');return
        try:
            amount=f"{row['amount']//SAT}.{row['amount']%SAT:08d}"
            response=self.local('execute_transfer',{'wallet_name':self.config['wallet_name'],'password':self.config['password'],'target_hex':row['address'],'amount_qbtc':amount})
            txid=response.get('tx_hash')
            if not response.get('success') or not isinstance(txid,str) or len(txid)!=64:
                raise ValueError('Node did not return a successful transaction receipt')
            bytes.fromhex(txid)
            self.db.execute("UPDATE receipts SET state='broadcast',txid=? WHERE id=?",(txid,row['id']))
            self.ledger.submitted(row['id'],txid)
        except Exception:
            self.db.execute("UPDATE receipts SET state='unknown' WHERE id=?",(row['id'],))
            self.ledger.uncertain(row['id'],'Transaction outcome unknown; manual reconciliation required')
            raise ValueError('Transfer outcome unknown; no automatic resend') from None
        self.status('ready')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args()
    signer=Signer(json.loads(pathlib.Path(args.config).read_text()))
    while True:
        try:signer.cycle()
        except Exception as error:signer.status('paused',str(error)[:180])
        time.sleep(30)
