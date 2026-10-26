import http.server
import json
import pathlib
import urllib.parse
from core import OWNER,address_hash,rpc

class Handler(http.server.BaseHTTPRequestHandler):
    rpc_token=None
    def log_message(self,*args):pass
    def do_GET(self):self.forward()
    def do_POST(self):self.forward()
    def forward(self):
        try:
            path=urllib.parse.urlsplit(self.path).path
            method=path.removeprefix('/api/')
            if path!='/api/'+method:raise ValueError('Invalid path')
            length=int(self.headers.get('Content-Length',0))
            if not 0<=length<=4*1024*1024:raise ValueError('Request too large')
            body=json.loads(self.rfile.read(length)) if length else None
            if method=='get_info':body=None
            elif method=='get_block':
                if type(body.get('height')) is not int or not 0<=body['height']<=10_000_000:raise ValueError('Invalid height')
                body={'height':body['height']}
            elif method=='get_block_template':body={'miner_address':OWNER}
            elif method=='get_balance':
                address_hash(body['address']);body={'address':body['address']}
            elif method=='submit_block':
                if not isinstance(body.get('block'),dict):raise ValueError('Invalid block')
                body={'block':body['block']}
            else:raise ValueError('RPC method unavailable')
            data=json.dumps(rpc('http://127.0.0.1:24002',method,body,self.rpc_token)).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        except Exception:
            self.send_error(400,'RPC request rejected')

if __name__=='__main__':
    Handler.rpc_token=json.loads(pathlib.Path('/etc/lackpool/rpc-proxy.json').read_text())['rpc_token']
    http.server.ThreadingHTTPServer(('127.0.0.1',24003),Handler).serve_forever()
