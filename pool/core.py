import hashlib
import json
import struct
import time
import urllib.error
import urllib.request

SAT = 100_000_000
OWNER = 'qbtc10y29nvfuwyxfxhkl4yqkenw4u6hshsk9zgaf5ctz4zfpa2gxe45qtwawce'
CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'

def address_hash(address):
    if not isinstance(address,str) or address.lower()!=address or not address.startswith('qbtc1'):
        raise ValueError('Expected a Q-BTC address')
    values=[CHARSET.index(c) for c in address[5:]]
    chk=1
    for value in [3,3,3,3,0,17,2,20,3]+values:
        top=chk>>25;chk=((chk&0x1ffffff)<<5)^value
        for bit,generator in enumerate((0x3b6a57b2,0x26508e6d,0x1ea119fa,0x3d4233dd,0x2a1462b3)):
            if top>>bit&1:chk^=generator
    if chk!=0x2bc830a3:
        raise ValueError('Invalid Q-BTC address checksum')
    acc=bits=0;out=[]
    for value in values[:-6]:
        acc=(acc<<5)|value;bits+=5
        while bits>=8:
            bits-=8;out.append((acc>>bits)&255)
    if len(out)!=32 or bits>=5 or ((acc<<(8-bits))&255):
        raise ValueError('Invalid Q-BTC address size')
    return bytes(out)

def rpc(base,method,body=None,token=None,timeout=8):
    headers={'Content-Type':'application/json','Cache-Control':'no-cache','User-Agent':'LackPool/0.3.0'}
    if token:headers['Authorization']='Bearer '+token
    data=None if body is None else json.dumps(body,separators=(',',':')).encode()
    request=urllib.request.Request(base.rstrip('/')+'/api/'+method+'?_='+str(time.time_ns()),data=data,headers=headers)
    with urllib.request.urlopen(request,timeout=timeout) as response:
        raw=response.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise ValueError('Node response too large')
        return json.loads(raw)

def vector(data):
    return struct.pack('<Q',len(data))+bytes(data)

def transaction_bytes(tx,witness=False):
    out=struct.pack('<Q',len(tx['inputs']))
    for item in tx['inputs']:
        out+=bytes(item['previous_output_hash'])+struct.pack('<I',item['vout'])
    out+=struct.pack('<Q',len(tx['outputs']))
    for item in tx['outputs']:
        out+=struct.pack('<Q',item['value'])+bytes(item['public_key_hash'])
        recovery=item.get('recovery')
        out+=b'\0' if recovery is None else b'\1'+bytes(recovery['recovery_hash'])+struct.pack('<Q',recovery['recovery_delay'])
    if witness:
        out+=struct.pack('<Q',len(tx['witnesses']))
        for item in tx['witnesses']:
            out+=vector(item['signature'])+vector(item['public_key'])
    return out

def merkle(layer):
    if not layer:return bytes(32)
    while len(layer)>1:
        layer=[hashlib.sha256(layer[i]+layer[min(i+1,len(layer)-1)]).digest() for i in range(0,len(layer),2)]
    return layer[0]

def roots(transactions):
    return tuple(merkle([hashlib.sha256(transaction_bytes(tx,witness)).digest() for tx in transactions]) for witness in (False,True))

def header_bytes(header):
    def hash_bytes(value):return bytes.fromhex(value) if isinstance(value,str) else bytes(value)
    return struct.pack('>Q',header['timestamp'])+b''.join(hash_bytes(header[k]) for k in ['previous_hash','merkle_root','commit_merkle_root'])+struct.pack('>QQ',header['nonce'],header['target'])

def block_digest(block):
    return hashlib.sha256(header_bytes(block.get('header',block))).hexdigest()

def public_block_to_full(block):
    transactions=[]
    for tx in block['transactions']:
        if tx.get('witness_size_bytes')!=0:
            raise ValueError('Explorer does not expose signed transaction witnesses; waiting for P2P sync')
        item={'inputs':[{'previous_output_hash':list(bytes.fromhex(i['prev_txid'])),'vout':i['vout']} for i in tx['inputs']],
              'outputs':[{'value':o['value_sats'],'public_key_hash':list(bytes.fromhex(o['address_hash'])),'recovery':None} for o in tx['outputs']],
              'witnesses':[{'signature':[],'public_key':[]} for _ in tx['inputs']]}
        if hashlib.sha256(transaction_bytes(item)).hexdigest()!=tx['txid']:
            raise ValueError('Explorer transaction does not match its txid')
        transactions.append(item)
    tx_root,witness_root=roots(transactions)
    if tx_root.hex()!=block['merkle_root'] or witness_root.hex()!=block['commit_merkle_root']:
        raise ValueError('Explorer Merkle roots do not match')
    header={k:list(bytes.fromhex(block[k])) for k in ['previous_hash','merkle_root','commit_merkle_root']}
    header.update({k:block[k] for k in ['timestamp','nonce','target']})
    if int(block_digest({'header':header})[:16],16)>header['target']:raise ValueError('Invalid public PoW')
    return {'header':header,'transactions':transactions}
