import json
import hashlib
import os
import pathlib
import random
import tempfile
import unittest

from accounting import Ledger
from core import OWNER,SAT,address_hash,block_digest,header_bytes,merkle,transaction_bytes
from payout import Signer,verify_payment
import test_payout

OTHER='qbtc1xvenxvenxvenxvenxvenxvenxvenxvenxvenxvenxvenxvenxvesvcddth'

class PplnsTests(unittest.TestCase):
    def ledger(self):
        ledger=Ledger(':memory:');ledger.configure_policy('PPLNS')
        self.addCleanup(ledger.db.close)
        return ledger

    def test_partial_boundary_has_exact_weight(self):
        ledger=self.ledger()
        ledger.share('a','older','w',1,0,(1<<62)-1)
        ledger.share('b','newer','w',1,1,(1<<63)-1)
        weights,first,filled=ledger.window_weights(2,5)
        self.assertEqual((weights,first,filled),({'newer':2,'older':3},1,5))

    def test_window_survives_block_boundary_and_orphan(self):
        ledger=self.ledger();ledger.share('a','older','w',1,0,(1<<63)-1)
        ledger.found('one',100,50*SAT,{},(1<<63)-1)
        ledger.share('b','newer','w',1,1,(1<<63)-1)
        ledger.found('two',101,50*SAT,{},(1<<63)-1)
        row=ledger.db.execute("SELECT allocations FROM blocks WHERE hash='two'").fetchone()
        self.assertEqual(json.loads(row[0]),{'older':2_462_500_000,'newer':2_462_500_000})
        ledger.observe('two','other',201)
        self.assertEqual(ledger.window_weights(2,4)[0],{'newer':2,'older':2})

    def test_startup_uses_available_work_without_inventing_miners(self):
        ledger=self.ledger();ledger.share('a','miner','w',1,0,(1<<63)-1)
        ledger.found('one',1,50*SAT,{},(1<<60)-1)
        self.assertEqual(json.loads(ledger.db.execute('SELECT allocations FROM blocks').fetchone()[0]),{'miner':4_925_000_000})

    def test_activation_excludes_old_unverified_shares(self):
        ledger=self.ledger();ledger.share('a','old','w',1,0,100)
        ledger.configure_policy('PPLNS',1)
        ledger.share('b','new','w',1,1,(1<<63)-1)
        ledger.found('one',1,50*SAT,{},100)
        self.assertEqual(set(json.loads(ledger.db.execute('SELECT allocations FROM blocks').fetchone()[0])),{'new'})

    def test_randomized_windows_and_rounding_conserve_reward(self):
        rng=random.Random(732)
        for iteration in range(100):
            ledger=self.ledger();shares=[]
            for i in range(rng.randint(1,40)):
                address=str(rng.randrange(5));power=rng.randrange(1,12);work=1<<power
                ledger.share(str(i),address,'w',1,i,(1<<(64-power))-1);shares.append((address,work))
            window=rng.randint(1,10000);remaining=window;expected={}
            for address,work in reversed(shares):
                used=min(remaining,work);expected[address]=expected.get(address,0)+used;remaining-=used
                if not remaining:break
            weights,first,filled=ledger.window_weights(len(shares),window)
            self.assertEqual(weights,expected);self.assertEqual(filled,min(window,sum(w for _,w in shares)))
            reward=rng.randrange(1,50*SAT);allocations=Ledger.split(reward,weights)
            self.assertEqual(sum(allocations.values()),reward)
            self.assertTrue(all(type(v) is int and v>=0 for v in allocations.values()))
            ledger.db.close()

    def signer_fixture(self,folder):
        root=pathlib.Path(folder)
        signer=Signer({'owner':OWNER,'database':str(root/'ledger.sqlite3'),'journal':str(root/'journal.sqlite3'),
                       'payout_scheme':'PPLNS','pplns_start_share':0,'status_file':str(root/'status.json'),
                       'protected_balance_sats':100*SAT,'wallet_name':'test','password':'test'})
        signer.ledger.configure_policy('PPLNS')
        block=test_payout.RewardProofTests().block()
        for nonce,address in [(0,OTHER),(1,OWNER)]:
            block['nonce']=nonce
            signer.ledger.share(block_digest(block),address,'w',1,nonce,block['target'],header_bytes(block).hex(),100)
        signer.ledger.found(block_digest(block),100,50*SAT,{},block['target'])
        row=signer.ledger.db.execute('SELECT * FROM blocks').fetchone()
        return signer,block,row

    def test_signer_independently_accepts_real_share_proofs(self):
        with tempfile.TemporaryDirectory() as folder:
            signer,block,row=self.signer_fixture(folder)
            self.assertEqual(signer.verify_allocations(row,block),75_000_000)
            signer.db.close();signer.ledger.db.close()

    def test_redirected_allocations_are_rejected_even_when_total_is_correct(self):
        with tempfile.TemporaryDirectory() as folder:
            signer,block,row=self.signer_fixture(folder)
            signer.ledger.db.execute('UPDATE blocks SET allocations=?',(json.dumps({OWNER:4_925_000_000}),))
            row=signer.ledger.db.execute('SELECT * FROM blocks').fetchone()
            with self.assertRaisesRegex(ValueError,'allocations'):signer.verify_allocations(row,block)
            signer.db.close();signer.ledger.db.close()

    def test_fake_share_hash_and_difficulty_are_rejected(self):
        for statement in ["UPDATE shares SET digest='bad' WHERE id=1",'UPDATE shares SET work=123 WHERE id=1',"UPDATE share_proofs SET header='00' WHERE share_id=1"]:
            with tempfile.TemporaryDirectory() as folder:
                signer,block,row=self.signer_fixture(folder);signer.ledger.db.execute(statement)
                with self.assertRaises(ValueError):signer.verify_allocations(row,block)
                signer.db.close();signer.ledger.db.close()

    def test_changed_window_and_cutoff_are_rejected(self):
        for statement in ["UPDATE block_policy SET window_work='999'",'UPDATE block_policy SET start_share=1','UPDATE blocks SET cutoff=1']:
            with tempfile.TemporaryDirectory() as folder:
                signer,block,row=self.signer_fixture(folder);signer.ledger.db.execute(statement)
                row=signer.ledger.db.execute('SELECT * FROM blocks').fetchone()
                with self.assertRaises(ValueError):signer.verify_allocations(row,block)
                signer.db.close();signer.ledger.db.close()

    def test_pending_incoming_coins_cannot_bypass_old_balance_floor(self):
        with tempfile.TemporaryDirectory() as folder:
            signer,block,row=self.signer_fixture(folder)
            signer.verify_chain=lambda:200;signer.reconcile=lambda tip:None
            signer.db.execute('INSERT INTO verified VALUES (?,?,?,?,?)',('proof',100,50*SAT,75_000_000,json.dumps({OTHER:20*SAT})))
            signer.ledger.db.execute('INSERT INTO balances(address,available) VALUES (?,?)',(OTHER,20*SAT))
            calls=[]
            def local(method,body=None):
                calls.append(method)
                if method=='wallet_unlock':return {'success':True,'address':OWNER}
                if method=='get_balance':return {'confirmed_sats':100*SAT,'locked_sats':0,'pending_sats':1000*SAT,'max_send_sats':100*SAT,'max_send_fee_sats':1000}
                raise AssertionError('Old funds must never reach transfer RPC')
            signer.local=local;signer.cycle();self.assertNotIn('execute_transfer',calls)
            self.assertIn('Protected',json.loads(pathlib.Path(signer.config['status_file']).read_text())['reason'])
            signer.db.close();signer.ledger.db.close()

    def test_crash_between_claim_and_private_intent_halts(self):
        with tempfile.TemporaryDirectory() as folder:
            signer,block,row=self.signer_fixture(folder)
            signer.ledger.db.execute('INSERT INTO balances(address,available) VALUES (?,?)',(OTHER,20*SAT))
            signer.ledger.queue_payouts();signer.ledger.claim()
            signer.verify_chain=lambda:self.fail('Interrupted payout must halt before RPC')
            with self.assertRaisesRegex(ValueError,'Interrupted'):signer.cycle()
            signer.db.close();signer.ledger.db.close()

    def test_equal_height_with_different_tip_hash_pauses_payouts(self):
        with tempfile.TemporaryDirectory() as folder:
            signer,block,row=self.signer_fixture(folder)
            def endpoint(different):
                def call(method,body=None):
                    if method=='get_info':return {'current_height':200}
                    return dict(block,nonce=99 if different else block['nonce'])
                return call
            signer.local=endpoint(False);signer.public=endpoint(True)
            with self.assertRaisesRegex(ValueError,'tip hashes'):signer.verify_chain()
            signer.db.close();signer.ledger.db.close()

    def test_crash_after_private_verification_recovers_missing_credit(self):
        with tempfile.TemporaryDirectory() as folder:
            signer,block,row=self.signer_fixture(folder);signer.config['activation_height']=100
            signer.db.execute('INSERT INTO verified VALUES (?,?,?,?,?)',(row['hash'],row['height'],row['reward'],row['fee'],row['allocations']))
            def endpoint(method,body=None):return {'current_height':200} if method=='get_info' else block
            signer.local=endpoint;signer.public=endpoint
            signer.verify_chain();signer.verify_chain()
            self.assertEqual(signer.ledger.summary(OWNER)['available_sats'],2_462_500_000)
            signer.db.close();signer.ledger.db.close()

    @unittest.skipUnless(os.name=='posix','POSIX symlink permissions')
    def test_status_update_does_not_follow_predictable_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            signer,block,row=self.signer_fixture(folder);root=pathlib.Path(folder)
            protected=root/'private';protected.write_text('unchanged')
            (root/'status.tmp').symlink_to(protected)
            signer.status('ready');self.assertEqual(protected.read_text(),'unchanged')
            self.assertEqual(json.loads((root/'status.json').read_text())['state'],'ready')
            signer.db.close();signer.ledger.db.close()

    def payment_block(self,address=OTHER,amount=20*SAT):
        tx={'inputs':[{'previous_output_hash':[17]*32,'vout':0}],
            'outputs':[{'value':amount,'public_key_hash':list(address_hash(address)),'recovery':None},
                       {'value':5*SAT,'public_key_hash':list(address_hash(OWNER)),'recovery':None}],'witnesses':[]}
        digest=hashlib.sha256(transaction_bytes(tx)).hexdigest()
        block={'height':201,'timestamp':1700000000,'previous_hash':'00'*32,'commit_merkle_root':'00'*32,'target':(1<<64)-1,'nonce':0,
               'merkle_root':merkle([bytes.fromhex(digest)]).hex(),'transactions':[{'txid':digest,'inputs':[{'prev_txid':'11'*32,'vout':0}],
               'outputs':[{'value_sats':item['value'],'address_hash':bytes(item['public_key_hash']).hex()} for item in tx['outputs']]}]}
        return block,{'address':OTHER,'amount':20*SAT,'txid':digest}

    def test_payment_requires_exact_recipient_amount_and_merkle_proof(self):
        block,receipt=self.payment_block();self.assertTrue(verify_payment(block,receipt,OWNER))
        for address,amount in [(OWNER,20*SAT),(OTHER,19*SAT)]:
            block,receipt=self.payment_block(address,amount)
            with self.assertRaises(ValueError):verify_payment(block,receipt,OWNER)
        block,receipt=self.payment_block();block['merkle_root']='ff'*32
        with self.assertRaises(ValueError):verify_payment(block,receipt,OWNER)

    def test_matured_earnings_send_once_and_confirm_without_touching_old_funds(self):
        with tempfile.TemporaryDirectory() as folder:
            signer,reward,row=self.signer_fixture(folder)
            signer.db.execute('INSERT INTO verified VALUES (?,?,?,?,?)',(row['hash'],100,row['reward'],row['fee'],json.dumps({OTHER:20*SAT})))
            signer.ledger.db.execute('INSERT INTO balances(address,available) VALUES (?,?)',(OTHER,20*SAT))
            payment,receipt=self.payment_block();calls=[];height=[200]
            signer.verify_chain=lambda:height[0]
            def local(method,body=None):
                calls.append((method,body))
                if method=='wallet_unlock':return {'success':True,'address':OWNER}
                if method=='get_balance':return {'confirmed_sats':150*SAT,'locked_sats':0,'pending_sats':0,'max_send_sats':100*SAT,'max_send_fee_sats':1_000_000}
                if method=='execute_transfer':return {'success':True,'tx_hash':receipt['txid']}
                if method=='get_block':return payment if body['height']==201 else reward
                raise AssertionError(method)
            signer.local=local;signer.public=lambda method,body=None:payment
            signer.cycle();height[0]=206;signer.cycle();signer.cycle()
            sends=[body for method,body in calls if method=='execute_transfer']
            self.assertEqual(len(sends),1);self.assertEqual(sends[0]['target_hex'],OTHER);self.assertEqual(sends[0]['amount_qbtc'],'20.00000000')
            self.assertEqual(signer.ledger.summary(OTHER)['paid_sats'],20*SAT)
            self.assertEqual(signer.db.execute('SELECT state FROM receipts').fetchone()[0],'confirmed')
            signer.db.close();signer.ledger.db.close()

    def test_lost_transfer_response_creates_unknown_receipt_and_never_retries(self):
        with tempfile.TemporaryDirectory() as folder:
            signer,block,row=self.signer_fixture(folder)
            signer.db.execute('INSERT INTO verified VALUES (?,?,?,?,?)',(row['hash'],100,row['reward'],row['fee'],json.dumps({OTHER:20*SAT})))
            signer.ledger.db.execute('INSERT INTO balances(address,available) VALUES (?,?)',(OTHER,20*SAT))
            signer.verify_chain=lambda:200;calls=[]
            def local(method,body=None):
                calls.append(method)
                if method=='wallet_unlock':return {'success':True,'address':OWNER}
                if method=='get_balance':return {'confirmed_sats':150*SAT,'locked_sats':0,'pending_sats':0,'max_send_sats':100*SAT,'max_send_fee_sats':1_000_000}
                if method=='execute_transfer':raise TimeoutError('lost response')
                raise AssertionError(method)
            signer.local=local
            with self.assertRaises(ValueError):signer.cycle()
            with self.assertRaises(ValueError):signer.cycle()
            self.assertEqual(calls.count('execute_transfer'),1)
            self.assertEqual(signer.db.execute('SELECT state FROM receipts').fetchone()[0],'unknown')
            signer.db.close();signer.ledger.db.close()

if __name__=='__main__':unittest.main()
