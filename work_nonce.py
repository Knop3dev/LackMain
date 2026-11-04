import copy
from reference import pow_bytes, split_job as legacy_split_job
KEY = 'work_nonce'

def nonce_field(block):
    return KEY if KEY in block else 'nonce'

def get_nonce(block):
    value = block[nonce_field(block)]
    if type(value) is not int or not 0 <= value < 2 ** 64:
        raise ValueError('Invalid work nonce')
    return value

def with_nonce(block, value):
    if type(value) is not int or not 0 <= value < 2 ** 64:
        raise ValueError('Invalid work nonce')
    return dict(block, **{nonce_field(block): value})

def attach_work_nonce(block):
    result = copy.deepcopy(block)
    result.pop('hash', None)
    result['nonce'] = 0
    result[KEY] = 10 ** 12
    result['mining_pad'] = ''
    raw = pow_bytes(result)
    marker = b'"work_nonce": '
    offset = raw.rfind(marker) + len(marker)
    result['mining_pad'] = '0' * ((40 - offset % 64) % 64)
    return result

def validate_work_nonce(block):
    if KEY not in block:
        return
    get_nonce(block)
    if type(block.get('nonce')) is not int or block['nonce'] != 0:
        raise ValueError('Extra work uses a fixed zero header nonce')
    pad = block.get('mining_pad')
    if not isinstance(pad, str) or len(pad) > 63 or any((c != '0' for c in pad)):
        raise ValueError('Invalid immutable mining pad')

def split_job(block):
    if KEY not in block:
        return legacy_split_job(block)
    validate_work_nonce(block)
    raw = pow_bytes(block)
    digits = str(get_nonce(block)).encode()
    marker = b'"work_nonce": '
    offset = raw.rfind(marker) + len(marker)
    if offset < len(marker) or raw[offset:offset + len(digits)] != digits:
        raise ValueError('Work nonce encoding mismatch')
    return (raw[:offset], raw[offset + len(digits):])
