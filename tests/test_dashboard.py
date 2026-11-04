import http.server, json, pathlib, sys, tempfile, threading, unittest, requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from config import Settings
from dashboard import Server
from miner import Miner

class DashboardTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.miner = Miner(Settings(devices=[], cpu_workers=1), self.directory.name)
        self.server = Server(self.miner, 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.session = requests.Session()
        self.session.trust_env = False

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.directory.cleanup()

    def headers(self):
        return {'Origin': self.url, 'X-Panel-Token': self.server.token}

    def test_no_csrf(self):
        self.assertEqual(self.session.post(self.url + '/api/start', json={}).status_code, 403)
        h = self.headers()
        h['Origin'] = 'https://example.com'
        self.assertEqual(self.session.post(self.url + '/api/start', json={}, headers=h).status_code, 403)

    def test_host_check(self):
        self.assertEqual(self.session.get(self.url + '/api/status', headers={'Host': 'attacker.example'}).status_code, 403)

    def test_settings(self):
        r = self.session.post(self.url + '/api/config', json={'intensity': 60}, headers=self.headers())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.session.get(self.url + '/api/status').json()['settings']['intensity'], 60)

    def test_secret_not_echoed(self):
        sentinel = 'DO_NOT_ECHO_THIS_PRIVATE_INPUT'
        r = self.session.post(self.url + '/api/unlock', json={'key': sentinel}, headers=self.headers())
        self.assertNotIn(sentinel, r.text)
        self.assertNotIn(sentinel, self.session.get(self.url + '/api/status').text)

    def test_empty_default(self):
        value = self.session.get(self.url + '/api/status').json()
        self.assertEqual(value['settings']['address'], '')
        self.assertFalse(value['running'])
        self.assertFalse(value['unlocked'])

    def test_static_assets(self):
        html = self.session.get(self.url + '/')
        self.assertIn(self.server.token, html.text)
        self.assertNotIn('PANEL_TOKEN', html.text)
        self.assertIn("frame-ancestors 'none'", html.headers['Content-Security-Policy'])
        self.assertEqual(self.session.get(self.url + '/app.js').status_code, 200)
if __name__ == '__main__':
    unittest.main()
