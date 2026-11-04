import base64, hashlib, json, pathlib
from ecdsa import SigningKey, SECP256k1
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def base58_encode(value):
    number = int.from_bytes(value, 'big')
    out = ''
    while number:
        number, r = divmod(number, 58)
        out = ALPHABET[r] + out
    return '1' * (len(value) - len(value.lstrip(b'\x00'))) + out

def valid_address(address):
    if not isinstance(address, str) or not 26 <= len(address) <= 35:
        return False
    try:
        number = 0
        for c in address:
            number = number * 58 + ALPHABET.index(c)
        value = b'\x00' * (len(address) - len(address.lstrip('1'))) + number.to_bytes((number.bit_length() + 7) // 8, 'big')
        return len(value) == 25 and value[0] == 0 and (hashlib.sha256(hashlib.sha256(value[:-4]).digest()).digest()[:4] == value[-4:])
    except (ValueError, OverflowError):
        return False

def address_from_key(key):
    digest = hashlib.sha256(key.get_verifying_key().to_string()).digest()
    raw = b'\x00' + hashlib.new('ripemd160', digest).digest()
    return base58_encode(raw + hashlib.sha256(hashlib.sha256(raw).digest()).digest()[:4])

def unlock(address, key_hex=None, wallet_file=None, password=None):
    try:
        if key_hex is not None:
            raw = bytes.fromhex(key_hex.strip().removeprefix('0x'))
        else:
            data = json.loads(pathlib.Path(wallet_file).read_text(encoding='utf-8-sig'))
            enc = data.get('encrypted', data.get('enc', data))
            kdf = PBKDF2HMAC(hashes.SHA256(), 32, base64.b64decode(enc['salt']), 600000)
            raw = AESGCM(kdf.derive(password.encode())).decrypt(base64.b64decode(enc['nonce']), base64.b64decode(enc['ct']), None)
            if len(raw) == 64:
                raw = bytes.fromhex(raw.decode('ascii'))
        key = SigningKey.from_string(raw, curve=SECP256k1)
        if address_from_key(key) != address:
            raise ValueError('mismatch')
        return key
    except Exception:
        raise ValueError('Unable to unlock this address: check the wallet and password or key') from None

def sign_block(key, block, address):
    if address_from_key(key) != address:
        raise ValueError('Signing address mismatch')
    message = f"BLOCK|{block['index']}|{block['hash']}|{address}"
    return {'X-Block-Signature': key.sign(message.encode(), hashfunc=hashlib.sha256).hex(), 'X-Block-Pubkey': key.get_verifying_key().to_string().hex()}
