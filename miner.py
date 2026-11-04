import atexit, collections, copy, dataclasses, hashlib, json, pathlib, queue, threading, time
from backend import OpenCL, list_devices
from config import Settings, save, data_directory
from cpu import CPU
from network import Node
from protocol import make_job, validate_candidate, validate_chain
from reference import pow_hash
from work_nonce import split_job, with_nonce
from wallet import unlock, sign_block
from submission import submission_kind, retry_delay, next_window
from pacing import DispatchPacer
from hardware import Hardware

class Miner:

    def __init__(self, settings=None, directory=None):
        self.settings = settings or Settings()
        self.directory = pathlib.Path(directory or data_directory())
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.key = None
        self.job = None
        self.base = 10 ** 12
        self.pending = None
        self.results = queue.Queue(maxsize=64)
        self.logs = collections.deque(maxlen=100)
        self.stats = {'state': 'Stopped', 'hashrate': 0, 'average_hashrate': 0, 'accepted': 0, 'rejected': 0, 'stale': 0, 'blocks': 0, 'devices': {}, 'node_height': None, 'balance_sats': None, 'pool': None, 'wait_until': None, 'error': None}
        self.total = 0
        self.started = 0
        self.samples = collections.deque(maxlen=120)
        self.hardware = Hardware()
        self.workers = []
        self.tuning_applied = False
        atexit.register(self.hardware.restore)
        self.user_stopped = True
        self.restart_history = []
        self.supervisor = threading.Thread(target=self.supervise, daemon=True)
        self.supervisor.start()

    def supervise(self):
        while True:
            time.sleep(1)
            if self.user_stopped or self.running() or (not self.settings.auto_restart) or (self.stats['state'] != 'Error'):
                continue
            self.restart_history = [t for t in self.restart_history if time.monotonic() - t < 600]
            if len(self.restart_history) >= 3:
                continue
            time.sleep(5)
            if self.user_stopped or self.running():
                continue
            self.restart_history.append(time.monotonic())
            self.log('Restarting after a miner error')
            try:
                self.start()
            except Exception:
                self.state(state='Error', error='Automatic restart failed')

    def log(self, message):
        with self.lock:
            self.logs.append({'time': time.time(), 'message': message})

    def state(self, **values):
        with self.lock:
            self.stats.update(values)

    def snapshot(self):
        with self.lock:
            result = copy.deepcopy(self.stats)
            result.update(settings=dataclasses.asdict(self.settings), unlocked=self.key is not None, running=self.running(), logs=list(self.logs))
            if self.stats['state'] != 'Mining':
                result['hashrate'] = 0
            return result

    def devices(self):
        return list_devices()

    def configure(self, value):
        with self.lock:
            if self.running():
                raise ValueError('Stop mining before changing settings')
            known = {f.name for f in dataclasses.fields(Settings)}
            if set(value) - known:
                raise ValueError('Unknown settings')
            updated = Settings(**{**dataclasses.asdict(self.settings), **value}).validate()
            if updated.address != self.settings.address:
                self.key = None
            save(self.directory / 'settings.json', updated)
            self.settings = updated

    def unlock(self, **values):
        self.settings.validate(require_address=True)
        key = unlock(self.settings.address, **values)
        with self.lock:
            self.key = key
        self.log('Wallet unlocked locally')

    def lock_wallet(self):
        if self.running():
            raise ValueError('Stop mining before locking the wallet')
        self.key = None

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        with self.lock:
            if self.running():
                raise ValueError('Mining is already running')
            self.settings.validate(require_address=True)
            if self.settings.mode == 'solo' and self.key is None:
                raise ValueError('Unlock your SOLO wallet locally')
            available = self.devices()
            if any((i >= len(available) for i in self.settings.devices)):
                raise ValueError('Selected OpenCL device is unavailable')
            self.stop_event.clear()
            self.job = None
            self.pending = None
            self.total = 0
            self.samples.clear()
            self.workers = []
            self.user_stopped = False
            while not self.results.empty():
                try:
                    self.results.get_nowait()
                except queue.Empty:
                    break
            self.stats.update(state='Connecting', error=None, devices={}, hashrate=0, average_hashrate=0, wait_until=None)
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        self.user_stopped = True
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=20)
        if self.running():
            raise RuntimeError('Mining is still stopping; wait for the current network request')
        self.state(state='Stopped', hashrate=0, wait_until=None)
        self.hardware.restore()
        self.tuning_applied = False

    def apply_tuning(self):
        if self.running():
            raise ValueError('Stop mining before applying GPU tuning')
        self.hardware.apply(self.devices(), self.settings.tuning)
        self.tuning_applied = True
        self.log('Requested GPU settings applied; previous settings will be restored on stop')

    def reserve(self, count):
        with self.lock:
            if not self.job or self.pending:
                return None
            if self.base + count >= 10 ** 13:
                raise RuntimeError('Nonce range exhausted: wait for a new job')
            start = self.base
            self.base += count
            return (self.job, start)

    def account(self, device, count, elapsed):
        with self.lock:
            self.total += count
            now = time.monotonic()
            row = self.stats['devices'].setdefault(str(device), {})
            row.update(hashrate=count / max(elapsed, 1e-06), hashes=row.get('hashes', 0) + count)
            self.samples.append((now, self.total))
            cutoff = now - 60
            while len(self.samples) > 2 and self.samples[1][0] < cutoff:
                self.samples.popleft()
            first = self.samples[0]
            self.stats['hashrate'] = (self.total - first[1]) / max(0.001, now - first[0])
            self.stats['average_hashrate'] = self.total / max(0.001, now - self.started)

    def worker(self, device):
        engine = None
        try:
            engine = CPU(self.settings.cpu_workers) if device == 'cpu' else OpenCL(device=device)
            if device != 'cpu':
                from selftest import check
                check(engine)
                self.log(str(device) + ': CPU/GPU self-test passed')
            size = min(self.settings.worksize, engine.max_workgroup)
            count = 4096 * self.settings.cpu_workers if device == 'cpu' else self.settings.batch
            pacer = DispatchPacer(self.settings.intensity)
            self.log(str(device) + ': ' + engine.name)
            while not self.stop_event.is_set():
                assignment = self.reserve(count)
                if assignment is None:
                    self.stop_event.wait(0.05)
                    continue
                job, base = assignment
                if device != 'cpu':
                    sensor = self.hardware.read(self.devices_cache[device])
                    limits = self.settings.tuning.get(str(device), {})
                    hot = sensor.get('hotspot_c')
                    temp = sensor.get('temperature_c')
                    power = sensor.get('power_w')
                    with self.lock:
                        self.stats['devices'].setdefault(str(device), {}).update(sensor)
                    if hot is not None and hot >= self.settings.max_hotspot or (temp is not None and temp >= self.settings.max_temperature) or (power is not None and limits.get('power_w') and (power > limits['power_w'])):
                        with self.lock:
                            self.stats['devices'][str(device)]['hashrate'] = 0
                        self.stop_event.wait(0.5)
                        continue
                head, tail = split_job(job['block'])
                started = time.perf_counter()
                hits = engine.search(head, tail, base, count, job['target'], size)
                elapsed = time.perf_counter() - started
                self.account(device, count, elapsed)
                for nonce in hits:
                    with self.lock:
                        if self.job is not job:
                            break
                    candidate = with_nonce(job['block'], nonce)
                    candidate['hash'] = pow_hash(candidate)
                    validate_candidate(job, candidate)
                    while not self.stop_event.is_set():
                        try:
                            self.results.put((job, candidate), timeout=0.1)
                            break
                        except queue.Full:
                            continue
                    if job['mode'] == 'solo':
                        break
                pacer.after_dispatch(elapsed, self.stop_event)
        except Exception as exc:
            self.state(error=str(exc), state='Error')
            self.log('Worker ' + str(device) + ': ' + str(exc))
            self.stop_event.set()
        finally:
            if engine:
                engine.close()

    def persist(self, candidate, deadline):
        path = self.directory / 'prepared.json'
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps({'address': self.settings.address, 'node': self.settings.node, 'block': candidate, 'deadline': deadline}), encoding='utf8')
        tmp.replace(path)

    def restore_pending(self, job):
        try:
            data = json.loads((self.directory / 'prepared.json').read_text())
            block = data['block']
            if data['address'] != self.settings.address or data['node'] != self.settings.node or block['previous_hash'] != job['parent']['hash']:
                return
            if block.get('difficulty') != job['block']['difficulty']:
                return
            restored = dict(job, block={k: v for k, v in block.items() if k != 'hash'})
            validate_candidate(restored, block)
            self.job = restored
            self.pending = (restored, block)
            self.stats['wait_until'] = max(block['timestamp'], min(data['deadline'], time.time() + 3600))
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def run(self):
        self.started = time.monotonic()
        self.samples.append((self.started, 0))
        node = Node(self.settings.node)
        tip = None
        last_poll = last_balance = 0
        last_good_poll = time.monotonic()
        opens = {}
        wait_attempt = 0
        signature = None
        try:
            self.devices_cache = {d['id']: d for d in self.devices()}
            for device in self.settings.devices + (['cpu'] if self.settings.cpu_workers else []):
                worker = threading.Thread(target=self.worker, args=(device,), daemon=True)
                worker.start()
                self.workers.append(worker)
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now - last_poll >= 2:
                    last_poll = now
                    try:
                        current = node.get('/api/chain/tip')
                        last_good_poll = time.monotonic()
                        if current.get('hash') != tip:
                            chain = node.get('/api/chain?limit=12')
                            chain = chain if isinstance(chain, list) else chain.get('chain', chain.get('blocks', []))
                            validate_chain(chain)
                            difficulty = node.get('/api/difficulty/next')
                            founder = node.get('/api/founder/stats')
                            mempool = node.get('/api/mempool')
                            pool = node.get('/api/pool/info') if self.settings.mode == 'pool' else None
                            job = make_job(chain, mempool, difficulty, founder, self.settings.address, self.settings.mode, pool)
                            with self.lock:
                                self.job = job
                                self.base = 10 ** 12
                                self.pending = None
                                signature = None
                                tip = chain[-1]['hash']
                                self.stats.update(node_height=chain[-1]['index'], state='Mining', error=None, wait_until=None)
                                if self.settings.mode == 'solo':
                                    self.restore_pending(job)
                            self.log('New ' + self.settings.mode + ' job ' + str(job['block']['index']))
                    except Exception as exc:
                        self.log('Connection: ' + type(exc).__name__)
                        self.state(state='Connecting', error=str(exc))
                        if now - last_good_poll > 10:
                            with self.lock:
                                self.job = None
                                tip = None
                        self.stop_event.wait(2)
                        continue
                if now - last_balance >= 30:
                    last_balance = now
                    try:
                        balance = node.get('/api/wallet/balances/' + self.settings.address)
                        self.state(balance_sats=balance.get('lbtc'))
                        if self.settings.mode == 'pool':
                            self.state(pool=node.get('/api/pool/stats'))
                    except Exception:
                        pass
                if not self.pending:
                    try:
                        job, candidate = self.results.get(timeout=0.05)
                    except queue.Empty:
                        continue
                    with self.lock:
                        if job is not self.job:
                            self.stats['stale'] += 1
                            continue
                    validate_candidate(job, candidate)
                    if self.settings.mode == 'pool':
                        try:
                            _, response = node.request('/api/pool/share', {'miner': self.settings.address, 'block': candidate})
                            if response.get('ok'):
                                with self.lock:
                                    self.stats['accepted'] += 1
                                    self.stats['blocks'] += int(bool(response.get('block')))
                                self.log('Pool share accepted' + (' (block)' if response.get('block') else ''))
                            else:
                                with self.lock:
                                    self.stats['rejected'] += 1
                                self.log('Pool share rejected: ' + str(response.get('error', 'unknown'))[:180])
                        except Exception:
                            self.log('Pool submission outcome unknown; not counted as accepted')
                        continue
                    self.pending = (job, candidate)
                    wait_attempt = 0
                    signature = None
                    deadline = max(candidate['timestamp'], opens.get(candidate['previous_hash'], 0))
                    self.state(state='Waiting', wait_until=deadline, hashrate=0)
                    self.persist(candidate, deadline)
                    self.log('CPU-verified solution ready for block ' + str(candidate['index']))
                if self.pending:
                    job, candidate = self.pending
                    deadline = self.stats.get('wait_until') or candidate['timestamp']
                    if time.time() < deadline:
                        self.stop_event.wait(min(0.05, deadline - time.time()))
                        continue
                    if candidate['previous_hash'] != tip:
                        with self.lock:
                            self.stats['stale'] += 1
                            self.pending = None
                        continue
                    if signature is None:
                        signature = sign_block(self.key, candidate, self.settings.address)
                    try:
                        check = node.get('/api/difficulty/next')
                        if check.get('height') != candidate['index'] or check.get('difficulty') != candidate['difficulty']:
                            tip = None
                            continue
                        started = time.perf_counter()
                        code, response = node.request('/api/block', candidate, signature)
                        elapsed = time.perf_counter() - started
                        outcome = submission_kind(code, response)
                    except Exception:
                        self.log('Block submission needs reconciliation')
                        self.state(wait_until=time.time() + 2)
                        last_poll = 0
                        continue
                    if outcome == 'accepted':
                        with self.lock:
                            self.stats['accepted'] += 1
                            self.stats['blocks'] += 1
                        opens = {candidate['hash']: next_window(time.time(), elapsed)}
                        proof = {'height': candidate['index'], 'hash': candidate['hash'], 'nonce': candidate['work_nonce'], 'payout_address': self.settings.address, 'node_response': response, 'block': candidate}
                        proofs = self.directory / 'blocks'
                        proofs.mkdir(exist_ok=True)
                        (proofs / (str(candidate['index']) + '.json')).write_text(json.dumps(proof, indent=2))
                        self.log('Block ' + str(candidate['index']) + ' accepted')
                        self.pending = None
                        tip = None
                        last_poll = 0
                        (self.directory / 'prepared.json').unlink(missing_ok=True)
                    elif outcome == 'wait':
                        wait_attempt += 1
                        deadline = time.time() + retry_delay(response, elapsed, wait_attempt)
                        self.state(state='Waiting', wait_until=deadline)
                        self.persist(candidate, deadline)
                    elif outcome in ('stale', 'refresh'):
                        if outcome == 'stale':
                            with self.lock:
                                self.stats['stale'] += 1
                        self.pending = None
                        tip = None
                        last_poll = 0
                        (self.directory / 'prepared.json').unlink(missing_ok=True)
                    else:
                        raise RuntimeError('Node rejected the block: ' + str(response.get('error', response.get('message', 'unknown')))[:180])
        except Exception as exc:
            self.state(state='Error', error=str(exc))
            self.log(str(exc))
        finally:
            self.stop_event.set()
            for worker in self.workers:
                worker.join(timeout=15)
            self.job = None
            self.state(hashrate=0)
            if self.stats['state'] != 'Error':
                self.state(state='Stopped')
