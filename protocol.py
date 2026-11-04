import copy, secrets, time
from reference import pow_hash, subsidy
from wallet import valid_address
from work_nonce import attach_work_nonce, split_job, with_nonce

def target(value):
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError('Invalid target')
    result = int(value, 16)
    if not 0 < result < 2 ** 256:
        raise ValueError('Invalid target')
    return result

def validate_chain(chain):
    if not isinstance(chain, list) or not chain:
        raise ValueError('Empty chain response')
    for i, b in enumerate(chain):
        if type(b.get('index')) is not int or pow_hash(b) != b.get('hash'):
            raise ValueError('Invalid public block hash')
        if b['index'] and int(b['hash'], 16) >= target(b['difficulty']):
            raise ValueError('Invalid public block PoW')
        if i and (b['index'] != chain[i - 1]['index'] + 1 or b['previous_hash'] != chain[i - 1]['hash']):
            raise ValueError('Inconsistent chain response')
    return chain

def make_job(chain, mempool, difficulty, founder, address, mode='solo', pool=None, now=None):
    validate_chain(chain)
    if not valid_address(address):
        raise ValueError('Invalid payout address')
    parent = chain[-1]
    height = parent['index'] + 1
    if difficulty.get('height') != height or founder.get('next_block_height') != height:
        raise ValueError('Node policy is behind the current height')
    network = target(difficulty['difficulty'])
    reward = subsidy(height)
    grant = founder.get('next_block_founder_units')
    recipient = founder.get('address')
    if type(grant) is not int or not 0 <= grant <= reward or (grant and (not valid_address(recipient))):
        raise ValueError('Invalid founder policy')
    stamp = max(int(time.time() if now is None else now), parent['timestamp'] + 180)
    if isinstance(mempool, dict):
        mempool = mempool.get('mempool', mempool.get('transactions', []))
    if not isinstance(mempool, list):
        raise ValueError('Invalid mempool')
    known = {tx.get('tx_hash') for b in chain for tx in b.get('transactions', [])}
    txs = copy.deepcopy([t for t in mempool if isinstance(t, dict) and t.get('sender') != 'coinbase' and (not t.get('tx_hash') or t['tx_hash'] not in known)][:48])
    if any((type(t.get('fee', 0)) is not int or t.get('fee', 0) < 0 for t in txs)):
        raise ValueError('Invalid mempool fees')
    fees = sum((t.get('fee', 0) for t in txs))
    outputs = []
    pay_to = address
    share_target = network
    if mode == 'pool':
        if not pool or not valid_address(pool.get('pool_address')):
            raise ValueError('Pool did not provide a valid reward address')
        factor = pool.get('share_factor', 16)
        if type(factor) is not int or not 1 <= factor <= 1000000:
            raise ValueError('Invalid pool share factor')
        pay_to = pool['pool_address']
        share_target = min(2 ** 256 - 1, network * factor)
    if grant:
        outputs.append({'sender': 'coinbase', 'recipient': recipient, 'amount': grant, 'fee': 0, 'timestamp': stamp, 'memo': f'founder_grant_block_{height}'})
    cb = {'sender': 'coinbase', 'recipient': pay_to, 'amount': reward - grant + fees, 'fee': fees, 'timestamp': stamp}
    if mode == 'pool':
        cb.update(memo='pool:' + address, extra=secrets.token_hex(6))
    outputs.append(cb)
    block = attach_work_nonce({'index': height, 'timestamp': stamp, 'previous_hash': parent['hash'], 'nonce': 0, 'difficulty': difficulty['difficulty'], 'transactions': outputs + txs})
    return {'block': block, 'target': share_target, 'network_target': network, 'parent': parent, 'address': address, 'mode': mode, 'pay_to': pay_to, 'founder': copy.deepcopy(founder)}

def validate_candidate(job, block):
    if block.get('index') != job['parent']['index'] + 1 or block.get('previous_hash') != job['parent']['hash']:
        raise ValueError('Candidate parent mismatch')
    if block.get('difficulty') != job['block']['difficulty'] or type(block.get('timestamp')) is not int or block['timestamp'] < job['parent']['timestamp'] + 180:
        raise ValueError('Candidate policy mismatch')
    coinbases = [t for t in block.get('transactions', []) if t.get('sender') == 'coinbase']
    policy = job['founder']
    grant = policy['next_block_founder_units']
    expected = 2 if grant else 1
    if len(coinbases) != expected or block['transactions'][:expected] != coinbases:
        raise ValueError('Unexpected coinbase outputs')
    if grant and (coinbases[0].get('recipient') != policy['address'] or coinbases[0].get('amount') != grant):
        raise ValueError('Founder payout changed')
    fees = sum((t.get('fee', 0) for t in block['transactions'][expected:]))
    if coinbases[-1].get('recipient') != job['pay_to'] or coinbases[-1].get('amount') != subsidy(block['index']) - grant + fees:
        raise ValueError('Miner payout changed')
    original = job['block']
    if {k: v for k, v in block.items() if k not in ('hash', 'work_nonce')} != {k: v for k, v in original.items() if k not in ('hash', 'work_nonce')}:
        raise ValueError('GPU candidate changed immutable work')
    digest = pow_hash(block)
    if block.get('hash') != digest or int(digest, 16) >= job['target']:
        raise ValueError('CPU verification failed')
    return digest
