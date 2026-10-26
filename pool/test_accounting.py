import unittest
from accounting import Ledger
from core import OWNER,SAT,address_hash

class AccountingTests(unittest.TestCase):
    def test_address_checksum(self):
        self.assertEqual(address_hash(OWNER).hex(),'791459b13c710c935edfa9016ccdd5e6af0bc2c5123a9a6162a8921ea906cd68')
        with self.assertRaises(ValueError):address_hash(OWNER[:-1]+'q')

    def ledger(self):
        ledger=Ledger(':memory:')
        ledger.share('a','worker-a','gpu0',1,1,(1<<31)-1)
        ledger.share('b','worker-b','gpu0',1,2,(1<<32)-1)
        ledger.found('block',100,50*SAT,{'success':True})
        return ledger

    def test_weighted_distribution_and_exact_fee(self):
        ledger=self.ledger();block=ledger.db.execute('SELECT * FROM blocks').fetchone()
        self.assertEqual(block['fee'],75_000_000)
        ledger.observe('block','block',199)
        self.assertEqual(ledger.summary('worker-a')['available_sats'],0)
        ledger.observe('block','block',200)
        a=ledger.summary('worker-a')['available_sats'];b=ledger.summary('worker-b')['available_sats']
        self.assertEqual(a+b,4_925_000_000)
        self.assertAlmostEqual(a/b,2,places=7)
        ledger.observe('block','block',201)
        self.assertEqual(ledger.summary('worker-a')['available_sats'],a)

    def test_orphan_never_becomes_spendable(self):
        ledger=self.ledger();ledger.observe('block','other',250)
        ledger.queue_payouts();self.assertIsNone(ledger.claim())
        self.assertEqual(ledger.summary('worker-a')['available_sats'],0)

    def test_payout_threshold_and_crash_do_not_repeat(self):
        ledger=self.ledger();ledger.observe('block','block',200);ledger.queue_payouts()
        first=ledger.claim();second=ledger.claim()
        self.assertNotEqual(first['id'],second['id']);self.assertIsNone(ledger.claim())
        ledger.uncertain(first['id'],'RPC timeout');self.assertIsNone(ledger.claim())
        self.assertGreaterEqual(first['amount'],10*SAT)
        ledger.submitted(first['id'],'txid');ledger.submitted(first['id'],'txid')
        self.assertEqual(ledger.db.execute('SELECT COUNT(*) FROM payouts WHERE txid=?',('txid',)).fetchone()[0],1)

    def test_reorganization_of_matured_reward_halts_payouts(self):
        ledger=self.ledger();ledger.observe('block','block',200);ledger.observe('block','fork',201)
        ledger.queue_payouts();self.assertIsNone(ledger.claim())

    def test_duplicate_work_is_not_paid_twice(self):
        ledger=Ledger(':memory:')
        self.assertIsNotNone(ledger.share('digest','a','w',1,2,100))
        self.assertIsNone(ledger.share('digest','b','w',2,2,100))

if __name__=='__main__':unittest.main()
