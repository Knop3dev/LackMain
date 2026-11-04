import json, requests, threading, time
from config import VERSION

class Node:

    def __init__(self, origin):
        self.origin = origin.rstrip('/')
        self.local = threading.local()
        self.cooldown = 0
        self.lock = threading.Lock()

    def session(self):
        if not hasattr(self.local, 'session'):
            self.local.session = requests.Session()
            self.local.session.headers.update({'User-Agent': 'lackminer-lbtc/' + VERSION, 'X-LBTC-Miner': '67', 'Accept': 'application/json'})
        return self.local.session

    def request(self, path, body=None, headers=None):
        with self.lock:
            if time.monotonic() < self.cooldown:
                raise RuntimeError('Node rate limit: waiting before reconnect')
        method = 'GET' if body is None else 'POST'
        r = self.session().request(method, self.origin + path, params={'_': time.time_ns()} if body is None else None, json=body, headers=headers, timeout=(4, 12))
        if r.status_code == 429:
            try:
                delay = max(5, min(600, float(r.headers.get('Retry-After', 30))))
            except ValueError:
                delay = 30
            with self.lock:
                self.cooldown = time.monotonic() + delay
        try:
            value = r.json()
        except ValueError:
            raise RuntimeError('Node returned a non-JSON response (HTTP ' + str(r.status_code) + ')') from None
        if body is None:
            r.raise_for_status()
        if not isinstance(value, (dict, list)):
            raise ValueError('Invalid node response')
        return (r.status_code, value)

    def get(self, path):
        return self.request(path)[1]
