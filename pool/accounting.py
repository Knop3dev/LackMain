import json
import sqlite3
import time
import uuid

from core import SAT

class Ledger:
    def __init__(self,path,fee_bps=150,min_payout=10*SAT,start_height=0):
        self.fee_bps=fee_bps;self.min_payout=min_payout
        self.db=sqlite3.connect(path,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.executescript('''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shares(id INTEGER PRIMARY KEY,digest TEXT UNIQUE NOT NULL,address TEXT NOT NULL,worker TEXT NOT NULL,job INTEGER NOT NULL,nonce TEXT NOT NULL,work INTEGER NOT NULL,created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS shares_created ON shares(created);
CREATE INDEX IF NOT EXISTS shares_address_created ON shares(address,created);
CREATE TABLE IF NOT EXISTS blocks(hash TEXT PRIMARY KEY,height INTEGER NOT NULL,reward INTEGER NOT NULL,fee INTEGER NOT NULL,cutoff INTEGER NOT NULL,round_start INTEGER NOT NULL,state TEXT NOT NULL,allocations TEXT NOT NULL,node_response TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS balances(address TEXT PRIMARY KEY,available INTEGER NOT NULL DEFAULT 0,paid INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS payouts(id TEXT PRIMARY KEY,address TEXT NOT NULL,amount INTEGER NOT NULL,state TEXT NOT NULL,txid TEXT UNIQUE,error TEXT,created REAL NOT NULL,updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS payouts_address ON payouts(address,created);
''')
        self.db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('round_start','0'))
        self.db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('start_height',str(start_height)))
        self.db.executescript('''
CREATE TABLE IF NOT EXISTS share_proofs(share_id INTEGER PRIMARY KEY,header TEXT NOT NULL,target TEXT NOT NULL,height INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS block_policy(hash TEXT PRIMARY KEY,scheme TEXT NOT NULL,start_share INTEGER NOT NULL,window_work TEXT NOT NULL,network_target TEXT NOT NULL);
''')
        self.scheme='PROP';self.policy_start=0;self.window_multiple=2

    def configure_policy(self,scheme='PROP',start_share=0,multiple=2):
        if scheme not in ('PROP','PPLNS') or type(start_share) is not int or start_share<0 or multiple!=2:
            raise ValueError('Invalid payout policy')
        self.scheme=scheme;self.policy_start=start_share;self.window_multiple=multiple

    def window_weights(self,cutoff,window,start_share=None):
        if type(window) is not int or window<=0:raise ValueError('Invalid PPLNS window')
        start=self.policy_start if start_share is None else start_share
        remaining=window;weights={};first=cutoff
        for row in self.db.execute('SELECT id,address,work FROM shares WHERE id>? AND id<=? ORDER BY id DESC',(start,cutoff)):
            used=min(remaining,row['work'])
            if used<=0:raise ValueError('Invalid share weight')
            weights[row['address']]=weights.get(row['address'],0)+used
            remaining-=used;first=row['id']
            if not remaining:break
        return weights,first,window-remaining

    def share(self,digest,address,worker,job,nonce,target,header=None,height=0):
        work=max(1,(1<<64)//(target+1))
        self.db.execute('BEGIN IMMEDIATE')
        try:
            cursor=self.db.execute('INSERT INTO shares(digest,address,worker,job,nonce,work,created) VALUES (?,?,?,?,?,?,?)',(digest,address,worker,job,str(nonce),work,time.time()))
            if header is not None:self.db.execute('INSERT INTO share_proofs VALUES (?,?,?,?)',(cursor.lastrowid,header,str(target),height))
            self.db.execute('COMMIT')
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            self.db.execute('ROLLBACK')
            return None
        except Exception:
            self.db.execute('ROLLBACK');raise

    @staticmethod
    def split(amount,weights):
        total=sum(weights.values())
        if total<=0:raise ValueError('No accepted work to reward')
        values={address:amount*weight//total for address,weight in weights.items()}
        remainder=amount-sum(values.values())
        ranking=sorted(weights,key=lambda address:(-(amount*weights[address]%total),address))
        for address in ranking[:remainder]:values[address]+=1
        return values

    def found(self,digest,height,reward,response,network_target=None):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute('SELECT 1 FROM blocks WHERE hash=?',(digest,)).fetchone():
                self.db.execute('ROLLBACK');return False
            start=int(self.db.execute("SELECT value FROM meta WHERE key='round_start'").fetchone()[0])
            cutoff=self.db.execute('SELECT COALESCE(MAX(id),0) FROM shares').fetchone()[0]
            window=0
            if self.scheme=='PPLNS':
                if type(network_target) is not int or not 0<=network_target<(1<<64):raise ValueError('Missing network target')
                window=self.window_multiple*max(1,(1<<64)//(network_target+1))
                weights,first,_=self.window_weights(cutoff,window)
                start=first-1
            else:
                weights={row['address']:row['work'] for row in self.db.execute('SELECT address,SUM(work) work FROM shares WHERE id>? AND id<=? GROUP BY address',(start,cutoff))}
            fee=reward*self.fee_bps//10000
            allocations=self.split(reward-fee,weights)
            self.db.execute('INSERT INTO blocks VALUES (?,?,?,?,?,?,?,?,?,?)',(digest,height,reward,fee,cutoff,start,'pending',json.dumps(allocations,sort_keys=True),json.dumps(response),time.time()))
            self.db.execute('INSERT INTO block_policy VALUES (?,?,?,?,?)',(digest,self.scheme,self.policy_start,str(window),str(network_target or 0)))
            self.db.execute("UPDATE meta SET value=? WHERE key='round_start'",(str(cutoff),))
            self.db.execute('COMMIT');return True
        except Exception:
            self.db.execute('ROLLBACK');raise

    def observe(self,digest,canonical_hash,tip,maturity=100):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            block=self.db.execute('SELECT * FROM blocks WHERE hash=?',(digest,)).fetchone()
            if not block or block['state']=='orphaned':
                self.db.execute('COMMIT');return
            if block['state']=='matured':
                if canonical_hash!=digest:
                    self.db.execute("INSERT OR REPLACE INTO meta VALUES ('safety_halt','Matured pool block was reorganized')")
                self.db.execute('COMMIT');return
            if canonical_hash!=digest:
                self.db.execute("UPDATE blocks SET state='orphaned' WHERE hash=?",(digest,))
                current=int(self.db.execute("SELECT value FROM meta WHERE key='round_start'").fetchone()[0])
                if current==block['cutoff']:
                    self.db.execute("UPDATE meta SET value=? WHERE key='round_start'",(str(block['round_start']),))
            elif tip>=block['height']+maturity:
                for address,amount in json.loads(block['allocations']).items():
                    self.db.execute('INSERT INTO balances(address,available) VALUES (?,?) ON CONFLICT(address) DO UPDATE SET available=available+excluded.available',(address,amount))
                self.db.execute("UPDATE blocks SET state='matured' WHERE hash=?",(digest,))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK');raise

    def queue_payouts(self):
        if self.db.execute("SELECT 1 FROM meta WHERE key='safety_halt'").fetchone():return
        self.db.execute('BEGIN IMMEDIATE')
        try:
            for row in self.db.execute('SELECT address,available FROM balances WHERE available>=? ORDER BY address',(self.min_payout,)).fetchall():
                payout_id=str(uuid.uuid4());now=time.time()
                self.db.execute('INSERT INTO payouts VALUES (?,?,?,?,?,?,?,?)',(payout_id,row['address'],row['available'],'queued',None,None,now,now))
                self.db.execute('UPDATE balances SET available=0 WHERE address=?',(row['address'],))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK');raise

    def claim(self):
        if self.db.execute("SELECT 1 FROM meta WHERE key='safety_halt'").fetchone():return None
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute("SELECT * FROM payouts WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row:self.db.execute("UPDATE payouts SET state='signing',updated=? WHERE id=?",(time.time(),row['id']))
            self.db.execute('COMMIT');return dict(row) if row else None
        except Exception:
            self.db.execute('ROLLBACK');raise

    def submitted(self,payout_id,txid):
        self.db.execute("UPDATE payouts SET state='broadcast',txid=?,updated=?,error=NULL WHERE id=? AND state IN ('signing','unknown','broadcast')",(txid,time.time(),payout_id))

    def uncertain(self,payout_id,error):
        self.db.execute("UPDATE payouts SET state='unknown',error=?,updated=? WHERE id=? AND state='signing'",(error[:200],time.time(),payout_id))

    def summary(self,address=None):
        totals=self.db.execute('SELECT COUNT(*) count,COALESCE(SUM(reward),0) reward,COALESCE(SUM(fee),0) fee FROM blocks WHERE state=\'matured\'').fetchone()
        paid=self.db.execute("SELECT COALESCE(SUM(amount),0) FROM payouts WHERE state='confirmed'").fetchone()[0]
        result={'pool_fee_percent':self.fee_bps/100,'minimum_payout_sats':self.min_payout,'maturity_blocks':100,'matured_blocks':totals['count'],'matured_reward_sats':totals['reward'],'pool_fee_sats':totals['fee'],'paid_sats':paid,
                'blocks':[dict(row) for row in self.db.execute('SELECT hash,height,reward,fee,state,created FROM blocks ORDER BY created DESC LIMIT 30')]}
        if address:
            row=self.db.execute('SELECT * FROM balances WHERE address=?',(address,)).fetchone()
            result['available_sats']=row['available'] if row else 0
            result['paid_sats']=row['paid'] if row else 0
            result['in_flight_sats']=self.db.execute("SELECT COALESCE(SUM(amount),0) FROM payouts WHERE address=? AND state NOT IN ('confirmed','retained')",(address,)).fetchone()[0]
            result['pending_sats']=sum(json.loads(row['allocations']).get(address,0) for row in self.db.execute("SELECT allocations FROM blocks WHERE state='pending'"))
            result['payouts']=[dict(row) for row in self.db.execute('SELECT id,amount,state,txid,created FROM payouts WHERE address=? ORDER BY created DESC LIMIT 30',(address,))]
        return result
