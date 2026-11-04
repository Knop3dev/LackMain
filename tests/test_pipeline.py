import hashlib, http.server, json, pathlib, sys, tempfile, threading, time, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ecdsa import SigningKey, SECP256k1, VerifyingKey
from config import Settings
from miner import Miner
from reference import pow_hash
from wallet import address_from_key

class NodeFixture(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(('127.0.0.1', 0), Handler)
        self.owner = SigningKey.generate(curve=SECP256k1)
        self.address = address_from_key(self.owner)
        self.founder = address_from_key(SigningKey.generate(curve=SECP256k1))
        self.pool = address_from_key(SigningKey.generate(curve=SECP256k1))
        b = {'index': 0, 'timestamp': int(time.time()) - 360, 'previous_hash': '0' * 64, 'difficulty': 'f' * 64, 'nonce': 0, 'transactions': []}
        b['hash'] = pow_hash(b)
        self.chain = [b]
        self.accepted = []

    def reply(self, handler, value, code=200):
        raw = json.dumps(value).encode()
        handler.send_response(code)
        handler.send_header('Content-Length', str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split('?')[0]
        s = self.server
        if path == '/api/chain/tip':
            v = s.chain[-1]
        elif path == '/api/chain':
            v = s.chain
        elif path == '/api/difficulty/next':
            v = {'height': s.chain[-1]['index'] + 1, 'difficulty': '000f' + 'f' * 60}
        elif path == '/api/founder/stats':
            v = {'next_block_height': s.chain[-1]['index'] + 1, 'next_block_founder_units': 50000000, 'address': s.founder}
        elif path == '/api/mempool':
            v = []
        elif path == '/api/pool/info':
            v = {'pool_address': s.pool, 'share_factor': 16}
        elif path == '/api/pool/stats':
            v = {}
        else:
            v = {'lbtc': 0}
        s.reply(self, v)

    def do_POST(self):
        s = self.server
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/api/pool/share':
            block = body['block']
            valid = pow_hash(block) == block.get('hash') and int(block['hash'], 16) < min(2 ** 256 - 1, int(block['difficulty'], 16) * 16)
            cb = block['transactions'][1]
            valid = valid and body['miner'] == s.address and (cb['memo'] == 'pool:' + s.address) and (cb['recipient'] == s.pool)
            if valid:
                s.accepted.append(('pool', block))
            s.reply(self, {'ok': bool(valid), 'block': False}, 200 if valid else 400)
            return
        block = body
        try:
            key = VerifyingKey.from_string(bytes.fromhex(self.headers['X-Block-Pubkey']), curve=SECP256k1)
            assert key.to_string() == s.owner.get_verifying_key().to_string()
            key.verify(bytes.fromhex(self.headers['X-Block-Signature']), f"BLOCK|{block['index']}|{block['hash']}|{s.address}".encode(), hashfunc=hashlib.sha256)
            assert pow_hash(block) == block['hash'] and int(block['hash'], 16) < int(block['difficulty'], 16)
            assert block['transactions'][1]['recipient'] == s.address and block['transactions'][1]['amount'] == 4950000000
            s.accepted.append(('solo', block))
            s.chain.append(block)
            s.reply(self, {'status': 'ok'})
        except Exception:
            s.reply(self, {'error': 'fixture verification failed'}, 400)

class PipelineTests(unittest.TestCase):

    def run_mode(self, mode):
        node = NodeFixture()
        threading.Thread(target=node.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory() as directory:
            miner = Miner(Settings(address=node.address, mode=mode, node='http://127.0.0.1:' + str(node.server_port), devices=[], cpu_workers=1, auto_restart=False), directory)
            if mode == 'solo':
                miner.unlock(key_hex=node.owner.to_string().hex())
            try:
                miner.start()
                deadline = time.monotonic() + 15
                while not node.accepted and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(node.accepted, miner.snapshot()['logs'])
                self.assertEqual(node.accepted[0][0], mode)
            finally:
                miner.stop()
                node.shutdown()
                node.server_close()

    def test_solo_pipeline(self):
        self.run_mode('solo')

    def test_pool_pipeline(self):
        self.run_mode('pool')
if __name__ == '__main__':
    unittest.main()
