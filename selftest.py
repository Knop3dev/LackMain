import hashlib, json, pathlib, sys, time
from reference import pow_hash
from work_nonce import attach_work_nonce, split_job, with_nonce

def example():
    return attach_work_nonce({'index': 1, 'timestamp': 1793491380, 'previous_hash': '0' * 64, 'difficulty': '0' * 8 + 'f' * 56, 'nonce': 0, 'transactions': [{'sender': 'coinbase', 'recipient': 'benchmark', 'amount': 5000000000, 'fee': 0, 'timestamp': 1793491380}]})

def check(engine):
    block = example()
    head, tail = split_job(block)
    tested = 0
    for base in (10 ** 12, 10 ** 12 + 999999990):
        want = [bytes.fromhex(pow_hash(with_nonce(block, base + i))) for i in range(32)]
        if engine.hashes(head, tail, base, 32) != want:
            raise RuntimeError('OpenCL CPU/GPU digest self-test failed')
        for target in (int.from_bytes(want[0], 'big'), int.from_bytes(want[0], 'big') + 1):
            expected = [base + i for i, h in enumerate(want) if int.from_bytes(h, 'big') < target]
            if sorted(engine.search(head, tail, base, 32, target, 1)) != expected:
                raise RuntimeError('OpenCL target comparison self-test failed')
        tested += 32
    return tested

def benchmark(engine, seconds, worksize, batch, stop=None, guard=None):
    block = example()
    head, tail = split_job(block)
    base = 10 ** 12
    hashes = 0
    engine.search(head, tail, base, batch, 0, worksize)
    started = time.perf_counter()
    while time.perf_counter() - started < seconds:
        if guard is not None:
            guard()
        if stop is not None and stop.is_set():
            break
        engine.search(head, tail, base, batch, 0, worksize)
        base += batch
        hashes += batch
    elapsed = time.perf_counter() - started
    return {'device': engine.name, 'hashes': hashes, 'seconds': elapsed, 'H_s': hashes / elapsed, 'CPU_GPU_match': True}
