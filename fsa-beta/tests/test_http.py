"""Local HTTP boundary tests. Created by ChatGPT (OpenAI)."""
import json
from pathlib import Path
import sys
import threading
import unittest
import urllib.request
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Handler,HTTPServer

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=HTTPServer(('127.0.0.1',0),Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def test_http_analyze_and_question(self):
        config=json.load(urllib.request.urlopen(self.base+'/api/config'))
        data=json.load(urllib.request.urlopen(self.base+'/api/demo'))
        for endpoint,extra in [('/api/analyze',{}),('/api/ask',{'question':'Explain accrual ratio'})]:
            req=urllib.request.Request(self.base+endpoint,data=json.dumps({'data':data,**extra}).encode(),headers={'Content-Type':'application/json','X-Beta-Token':config['token']})
            with urllib.request.urlopen(req) as r:self.assertEqual(r.status,200)
    def test_private_paths_not_served(self):
        for path in ['/engine.py','/.runtime/gemini.sqlite','/../server.py']:
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(self.base+path)
            self.assertEqual(e.exception.code,404)
    def test_missing_token_rejected(self):
        req=urllib.request.Request(self.base+'/api/analyze',data=b'{}',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
        self.assertEqual(e.exception.code,403)
    def test_cross_origin_rejected(self):
        req=urllib.request.Request(self.base+'/api/config',headers={'Origin':'https://example.com'})
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
        self.assertEqual(e.exception.code,403)
    def test_host_rejected(self):
        req=urllib.request.Request(self.base+'/api/config',headers={'Host':'attacker.example'})
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
        self.assertEqual(e.exception.code,403)
