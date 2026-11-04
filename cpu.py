import concurrent.futures, hashlib, multiprocessing, os

def scan(args):
    head, tail, base, count, target = args
    prefix = hashlib.sha256(head)
    hits = []
    for n in range(base, base + count):
        value = prefix.copy()
        value.update(str(n).encode())
        value.update(tail)
        if int.from_bytes(value.digest(), 'big') < target:
            hits.append(n)
    return hits

class CPU:
    name = 'CPU'
    max_workgroup = 1

    def __init__(self, workers=1):
        self.workers = min(workers, 61) if os.name == 'nt' else workers
        self.pool = concurrent.futures.ProcessPoolExecutor(self.workers, mp_context=multiprocessing.get_context('spawn'))

    def search(self, head, tail, base, count, target, worksize=1):
        step = (count + self.workers - 1) // self.workers
        jobs = [(head, tail, n, min(step, base + count - n), target) for n in range(base, base + count, step)]
        return [n for group in self.pool.map(scan, jobs) for n in group]

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)
