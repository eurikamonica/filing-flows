"""Loopback-only FSA Beta server. Created by ChatGPT (OpenAI)."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from engine import analyze
from gemini import explain
from student import answer

ROOT=Path(__file__).resolve().parent
TOKEN=secrets.token_urlsafe(32)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,obj,kind='application/json'):
        payload=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode() if kind=='application/json' else obj
        self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)));self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
    def trusted(self):
        host=self.headers.get('Host','')
        expected=f'127.0.0.1:{self.server.server_port}'
        return host==expected and self.headers.get('Origin',f'http://{expected}')==f'http://{expected}'
    def do_GET(self):
        if not self.trusted():return self.send(403,{'error':'Open this app on its printed loopback URL'})
        path=urlsplit(self.path).path
        if path=='/api/config':return self.send(200,{'token':TOKEN,'gemini_configured':bool(os.environ.get('FSA_BETA_GEMINI_KEY')),'author':'ChatGPT (OpenAI)'})
        if path=='/api/demo':return self.send(200,json.loads((ROOT/'examples/demo.json').read_text()))
        files={'/':'web/index.html','/app.js':'web/app.js','/style.css':'web/style.css'}
        if path not in files:return self.send(404,{'error':'Not found'})
        typ={'/':'text/html','/app.js':'text/javascript','/style.css':'text/css'}[path]
        self.send(200,(ROOT/files[path]).read_bytes(),typ)
    def do_POST(self):
        if not self.trusted() or self.headers.get('X-Beta-Token')!=TOKEN:return self.send(403,{'error':'Invalid local request'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=200000:raise ValueError('Request must be 1–200000 bytes')
            body=json.loads(self.rfile.read(length));report=analyze(body['data'])
            if self.path=='/api/analyze':result=report
            elif self.path=='/api/ask':result=answer(str(body.get('question',''))[:2000],report)
            elif self.path=='/api/explain':result=explain(report,ROOT/'.runtime')
            else:return self.send(404,{'error':'Not found'})
            self.send(200,result)
        except (ValueError,KeyError,TypeError,OverflowError) as e:self.send(400,{'error':str(e)})
        except Exception:self.send(500,{'error':'Beta processing failed; check input and local configuration'})

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8765);a=ap.parse_args()
    httpd=HTTPServer(('127.0.0.1',a.port),Handler)
    print(f'FSA Beta by ChatGPT (OpenAI): http://127.0.0.1:{a.port}',flush=True)
    httpd.serve_forever()
