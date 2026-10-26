import copy
import hashlib
import unittest
import tempfile
import pathlib
from core import OWNER,SAT,address_hash,block_digest,roots,transaction_bytes
from payout import verify_reward,Signer

class RewardProofTests(unittest.TestCase):
    def block(self):
        reward=50*SAT;marked=reward//3+61371;key=list(address_hash(OWNER))
        tx={'inputs':[{'previous_output_hash':[0]*32,'vout':100}],
            'outputs':[{'value':reward-marked,'public_key_hash':key,'recovery':None},{'value':marked,'public_key_hash':key,'recovery':None}],
            'witnesses':[{'signature':[],'public_key':[]}]}
        a,b=roots([tx])
        return {'height':100,'timestamp':1700000000,'previous_hash':'00'*32,'merkle_root':a.hex(),'commit_merkle_root':b.hex(),'nonce':0,'target':(1<<64)-1,
                'transactions':[{'txid':hashlib.sha256(transaction_bytes(tx)).hexdigest(),'inputs':[{'prev_txid':'00'*32,'vout':100}],
                                 'outputs':[{'value_sats':x['value'],'address_hash':bytes(x['public_key_hash']).hex()} for x in tx['outputs']]}]}

    def test_actual_marked_reward_is_verified(self):
        block=self.block();self.assertEqual(verify_reward(block,block_digest(block),100,50*SAT,OWNER),50*SAT)

    def test_invented_block_and_foreign_coinbase_are_rejected(self):
        block=self.block()
        with self.assertRaises(ValueError):verify_reward(block,'ff'*32,100,50*SAT,OWNER)
        bad=copy.deepcopy(block);bad['transactions'][0]['outputs'][0]['address_hash']='ff'*32
        with self.assertRaises(ValueError):verify_reward(bad,block_digest(bad),100,50*SAT,OWNER)

    def test_existing_ordinary_solo_reward_cannot_fund_pool_payouts(self):
        block=self.block();block['transactions'][0]['outputs']=[{'value_sats':50*SAT,'address_hash':address_hash(OWNER).hex()}]
        with self.assertRaises(ValueError):verify_reward(block,block_digest(block),100,50*SAT,OWNER)

    def test_fabricated_available_balance_does_not_trigger_a_transfer(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            signer=Signer({'owner':OWNER,'database':str(root/'ledger.sqlite3'),'journal':str(root/'private.sqlite3'),
                           'wallet_name':'test','password':'test'})
            signer.verify_chain=lambda:200
            calls=[]
            def local(method,body=None):
                calls.append(method)
                if method=='wallet_unlock':return {'success':True,'address':OWNER}
                raise AssertionError('Unverified earnings must never reach a payment RPC')
            signer.local=local
            signer.ledger.db.execute('INSERT INTO balances(address,available) VALUES (?,?)',(OWNER,20*SAT))
            with self.assertRaises(ValueError):signer.cycle()
            self.assertNotIn('execute_transfer',calls)
            signer.db.close();signer.ledger.db.close()

    def test_uncertain_transfer_is_never_automatically_repeated(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            signer=Signer({'owner':OWNER,'database':str(root/'ledger.sqlite3'),'journal':str(root/'private.sqlite3')})
            signer.db.execute('INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?)',('unknown',OWNER,10*SAT,1,'unknown',None,100,100,None,None))
            signer.verify_chain=lambda:self.fail('Uncertain transfer must stop the payout loop before any RPC')
            with self.assertRaises(ValueError):signer.cycle()
            signer.db.close();signer.ledger.db.close()

if __name__=='__main__':unittest.main()
