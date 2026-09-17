"""Opt-in message board on a working local network. No internet discovery or relay."""
import hmac
import ipaddress
import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from datetime import datetime,timezone
from pathlib import Path
from .storage import DATA,RESOURCES,read_json,write_json


class LocalBoard:
 def __init__(self):
  self.server=None;self.code='';self.address='';self.lock=threading.RLock()

 def state(self):
  with self.lock:
   return {'active':self.server is not None,'address':self.address,'code':self.code,'messages':read_json(DATA/'local-messages.json',[])[-200:]}

 def add(self,name,text):
  name=str(name).strip();text=str(text).strip()
  if not name or len(name)>80 or not text or len(text)>2000:raise ValueError('Enter a name and a message of up to 2,000 characters.')
  with self.lock:
   messages=read_json(DATA/'local-messages.json',[])
   messages.append({'name':name,'text':text,'at':datetime.now(timezone.utc).isoformat()})
   write_json(DATA/'local-messages.json',messages[-1000:])
  return self.state()

 def start(self,host=None):
  with self.lock:return self._start(host)

 def _start(self,host):
  if self.server:return self.state()
  if host is None:
   # Hostname resolution uses the current network. It neither sends a message nor
   # relies on an internet server; only RFC1918 addresses may host the board.
   try:addresses=socket.gethostbyname_ex(socket.gethostname())[2]
   except OSError:addresses=[]
   networks=[ipaddress.ip_network(v) for v in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]
   host=next((v for v in addresses if any(ipaddress.ip_address(v) in n for n in networks)),None)
   if not host:raise ValueError('Connect this device to a local Wi-Fi or Ethernet network, then start the board. Internet is not needed.')
  board=self;self.code=secrets.token_hex(4).upper()
  class Handler(BaseHTTPRequestHandler):
   def setup(self):
    super().setup();self.connection.settimeout(10)
   def log_message(self,*_):pass
   def reply(self,status,data,kind='application/json'):
    payload=json.dumps(data,ensure_ascii=False).encode() if kind=='application/json' else data
    self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Content-Length',str(len(payload)))
    self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
    self.end_headers();self.wfile.write(payload)
   def authorized(self):return hmac.compare_digest(self.headers.get('X-Board-Code',''),board.code)
   def do_GET(self):
    if self.path=='/':return self.reply(200,(RESOURCES/'local-board.html').read_bytes(),'text/html')
    if self.path!='/messages':return self.reply(404,{'error':'Not found'})
    if not self.authorized():return self.reply(401,{'error':'Enter the code shown in Jarvis.'})
    return self.reply(200,board.state()['messages'])
   def do_POST(self):
    if self.path!='/messages':return self.reply(404,{'error':'Not found'})
    if not self.authorized():return self.reply(401,{'error':'Enter the code shown in Jarvis.'})
    try:
     size=int(self.headers.get('Content-Length',0))
     if not 0<size<=10000:raise ValueError('Message is too large or empty.')
     data=json.loads(self.rfile.read(size));board.add(data.get('name',''),data.get('text',''))
     self.reply(200,{'saved':True})
    except (ValueError,TypeError,AttributeError):self.reply(400,{'error':'Enter a name and a message of up to 2,000 characters.'})
  self.server=ThreadingHTTPServer((host,0),Handler);self.server.daemon_threads=True
  self.address=f'http://{host}:{self.server.server_port}'
  threading.Thread(target=self.server.serve_forever,daemon=True).start()
  return self.state()

 def close(self):
  with self.lock:
   server=self.server;self.server=None;self.address='';self.code=''
  if server:server.shutdown();server.server_close()
