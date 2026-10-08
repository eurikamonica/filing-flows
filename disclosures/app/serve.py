from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser
root = Path(__file__).resolve().parents[1]/'docs'
url = 'http://127.0.0.1:8080'
print('Preview: '+url+'  (Ctrl+C to stop)')
webbrowser.open(url)
ThreadingHTTPServer(('127.0.0.1',8080), partial(SimpleHTTPRequestHandler,directory=str(root))).serve_forever()
