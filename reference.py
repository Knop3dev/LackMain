import hashlib, json

def pow_bytes(block):
    return json.dumps({k: v for k, v in block.items() if k != 'hash'}, sort_keys=True).encode()

def pow_hash(block):
    return hashlib.sha256(pow_bytes(block)).hexdigest()

def split_job(block):
    text = json.dumps({**{k: v for k, v in block.items() if k != 'hash'}, 'nonce': 0}, sort_keys=True)
    head, tail = text.split('"nonce": 0', 1)
    return ((head + '"nonce": ').encode(), tail.encode())

def subsidy(height):
    return 50 * 100000000 // 2 ** (height // 210000)
