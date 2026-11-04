import copy, dataclasses, hashlib, json, pathlib, secrets, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ecdsa import SigningKey, SECP256k1
from config import Settings, save, load
from wallet import valid_address, address_from_key, unlock
from reference import pow_hash
from work_nonce import attach_work_nonce, split_job, with_nonce
from protocol import make_job, validate_candidate, target
from selftest import example
from cpu import scan

class Tests(unittest.TestCase):

    def setUp(self):
        self.key = SigningKey.generate(curve=SECP256k1)
        self.address = address_from_key(self.key)
        self.founder = address_from_key(SigningKey.generate(curve=SECP256k1))

    def test_address(self):
        self.assertTrue(valid_address(self.address))
        self.assertFalse(valid_address(self.address[:-1] + '0'))
        self.assertFalse(valid_address(''))

    def test_ownership(self):
        self.assertEqual(unlock(self.address, key_hex=self.key.to_string().hex()).to_string(), self.key.to_string())
        with self.assertRaises(ValueError):
            unlock(self.founder, key_hex=self.key.to_string().hex())

    def test_stock_defaults(self):
        s = Settings()
        self.assertEqual(s.address, '')
        self.assertEqual(s.tuning, {})
        self.assertEqual(s.mode, 'solo')

    def test_settings_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / 'settings.json'
            s = Settings(address=self.address, devices=[0, 1], tuning={'0': {'core_mhz': None, 'power_percent': -10}})
            save(p, s)
            self.assertEqual(dataclasses.asdict(load(p)), dataclasses.asdict(s))
            self.assertNotIn('private_key', p.read_text())

    def test_endpoint_security(self):
        for node in ['http://remote.example', 'https://user:pass@example.com', 'https://example.com/?secret=x', 'file:///tmp']:
            with self.assertRaises(ValueError):
                Settings(node=node).validate()
        Settings(node='http://127.0.0.1:8000').validate()

    def test_bad_settings(self):
        for values in [{'devices': [0, 0]}, {'intensity': 101}, {'worksize': 7}, {'batch': 33}, {'cpu_workers': -1}, {'tuning': {'0': {'unknown': 1}}}, {'address': 'invalid'}]:
            with self.assertRaises(ValueError):
                Settings(**values).validate()

    def test_hash_vectors(self):
        root = pathlib.Path(__file__).parent
        for v in json.loads((root / 'vectors.json').read_text()):
            self.assertEqual(pow_hash(v['block']), v['hash'])

    def test_nonce_serialization(self):
        block = example()
        head, tail = split_job(block)
        for nonce in [10 ** 12, 10 ** 12 + 999999999, 10 ** 12 + 1000000000]:
            self.assertEqual(hashlib.sha256(head + str(nonce).encode() + tail).hexdigest(), pow_hash(with_nonce(block, nonce)))

    def parent(self):
        b = {'index': 0, 'timestamp': 1793491200, 'nonce': 0, 'difficulty': 'f' * 64, 'previous_hash': '0' * 64, 'transactions': []}
        b['hash'] = pow_hash(b)
        return b

    def job(self, mode='solo'):
        return make_job([self.parent()], [], {'height': 1, 'difficulty': 'f' * 64}, {'next_block_height': 1, 'next_block_founder_units': 50000000, 'address': self.founder}, self.address, mode, {'pool_address': self.founder, 'share_factor': 16}, now=1793491380)

    def test_solo_payout(self):
        job = self.job()
        tx = job['block']['transactions']
        self.assertEqual(tx[1]['recipient'], self.address)
        self.assertEqual(tx[1]['amount'], 4950000000)
        self.assertEqual(tx[0]['recipient'], self.founder)

    def test_pool_protocol(self):
        j = self.job('pool')
        coinbase = j['block']['transactions'][1]
        self.assertEqual(coinbase['recipient'], self.founder)
        self.assertEqual(coinbase['memo'], 'pool:' + self.address)
        self.assertEqual(len(coinbase['extra']), 12)
        self.assertEqual(j['target'], 2 ** 256 - 1)

    def test_immutable_payout(self):
        job = self.job()
        block = copy.deepcopy(job['block'])
        block['transactions'][1]['recipient'] = self.founder
        block['hash'] = pow_hash(block)
        with self.assertRaises(ValueError):
            validate_candidate(job, block)

    def test_cpu_search(self):
        j = self.job()
        head, tail = split_job(j['block'])
        self.assertEqual(scan((head, tail, 10 ** 12, 8, 2 ** 256 - 1)), list(range(10 ** 12, 10 ** 12 + 8)))

    def test_strict_comparison(self):
        block = example()
        head, tail = split_job(block)
        digest = int(pow_hash(with_nonce(block, 10 ** 12)), 16)
        self.assertEqual(scan((head, tail, 10 ** 12, 1, digest)), [])
        self.assertEqual(scan((head, tail, 10 ** 12, 1, digest + 1)), [10 ** 12])

    def test_policy_height(self):
        j = self.job()
        with self.assertRaises(ValueError):
            make_job([self.parent()], [], {'height': 3, 'difficulty': 'f' * 64}, {}, self.address)

    def test_target_bounds(self):
        for t in ['0' * 64, 'z' * 64, 'f' * 63]:
            with self.assertRaises(ValueError):
                target(t)
if __name__ == '__main__':
    unittest.main()
