import asyncio
import pathlib
import tempfile
import time
import unittest

from core import OWNER,address_hash,block_digest
from server import Pool
from test_pplns import OTHER

class SubmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.pool=Pool({'database':str(pathlib.Path(self.folder.name)/'ledger.sqlite3'),'node':'http://127.0.0.1:1','payout_scheme':'PPLNS'})
        self.pool.ready=True;self.pool.anchor='00'*32;self.pool.last_public_check=time.monotonic()
        self.session={'address':OWNER,'worker':'test','tag':1,'accepted':0}
        self.header={'timestamp':1700000000,'previous_hash':[0]*32,'merkle_root':[0]*32,'commit_merkle_root':[0]*32,'nonce':0,'target':0}
        self.pool.jobs[7]={'address':OWNER,'tag':1,'target':(1<<64)-1,'block':{'header':self.header,'transactions':[]},'height':100}

    async def asyncTearDown(self):
        self.pool.ledger.db.close();self.folder.cleanup()

    async def test_cpu_validated_share_has_durable_proof(self):
        nonce=1<<48
        self.assertTrue(await self.pool.submit(self.session,['test',7,nonce]))
        row=self.pool.ledger.db.execute('SELECT * FROM share_proofs').fetchone()
        self.assertEqual(row['height'],100);self.assertEqual(len(bytes.fromhex(row['header'])),120)
        with self.assertRaisesRegex(ValueError,'Duplicate'):await self.pool.submit(self.session,['test',7,nonce])

    async def test_cross_wallet_and_nonce_theft_rejected(self):
        self.session['address']=OTHER
        with self.assertRaisesRegex(ValueError,'Unknown job'):await self.pool.submit(self.session,['test',7,1<<48])
        self.session['address']=OWNER
        with self.assertRaisesRegex(ValueError,'range'):await self.pool.submit(self.session,['test',7,0])

    async def test_low_difficulty_stale_and_paused_work_rejected(self):
        self.pool.jobs[7]['target']=0
        with self.assertRaisesRegex(ValueError,'Low difficulty'):await self.pool.submit(self.session,['test',7,1<<48])
        self.pool.anchor='ff'*32
        with self.assertRaisesRegex(ValueError,'Stale'):await self.pool.submit(self.session,['test',7,1<<48])
        self.pool.ready=False
        with self.assertRaisesRegex(ValueError,'paused'):await self.pool.submit(self.session,['test',7,1<<48])
        self.assertEqual(self.pool.ledger.db.execute('SELECT COUNT(*) FROM shares').fetchone()[0],0)

    async def test_invalid_nonce_types_and_ranges_rejected(self):
        for nonce in [True,-1,1<<64,'123',None]:
            with self.assertRaises(ValueError):await self.pool.submit(self.session,['test',7,nonce])

    async def test_reconnected_share_cannot_be_paid_again(self):
        nonce=1<<48;await self.pool.submit(self.session,['test',7,nonce])
        self.pool.jobs[8]=dict(self.pool.jobs[7])
        with self.assertRaisesRegex(ValueError,'Duplicate'):await self.pool.submit(self.session,['test',8,nonce])

    async def test_saved_candidate_is_relayed_after_rpc_timeout(self):
        block={'header':dict(self.header),'transactions':[]};digest=block_digest(block)
        self.pool.ledger.share(digest,OWNER,'test',7,0,(1<<64)-1)
        self.pool.ledger.found(digest,100,50_000_000,{'state':'submitting','block':block},0)
        calls=[]
        async def call(base,method,body=None):
            calls.append((base,method,body));return {'success':True}
        self.pool.call=call
        self.assertTrue(await self.pool.replay_candidate({'current_height':100,'previous_hash':'00'*32}))
        self.assertEqual([base for base,_,_ in calls],[self.pool.node,self.pool.public])
        self.assertEqual(calls[0][2]['block'],block)

    async def test_http_invalid_address_is_400_and_private_paths_are_404(self):
        server=await asyncio.start_server(self.pool.http,'127.0.0.1',0)
        port=server.sockets[0].getsockname()[1]
        try:
            for path,expected in [('/api/miner/invalid','400 Bad Request'),('/../secrets/signer.json','404 Not Found')]:
                reader,writer=await asyncio.open_connection('127.0.0.1',port)
                writer.write(('GET '+path+' HTTP/1.1\r\nHost: localhost\r\n\r\n').encode());await writer.drain()
                response=await asyncio.wait_for(reader.read(),5)
                self.assertIn(expected.encode(),response.split(b'\r\n')[0])
                self.assertIn(b"frame-ancestors 'none'",response)
                writer.close();await writer.wait_closed()
        finally:server.close();await server.wait_closed()

if __name__=='__main__':unittest.main()
