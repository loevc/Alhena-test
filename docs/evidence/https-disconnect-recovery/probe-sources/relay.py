"""Loopback-only opaque HTTPS tunnel to GitHub for an owned network-recovery fixture.
No TLS interception or credential logging. Drop once after upstream data threshold;
block reconnects until the owned restore flag exists.
"""
import json,socket,socketserver,select,threading,time,sys
from pathlib import Path
config=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
evidence=Path(config['evidence']).resolve();root=Path(config['root']).resolve()
assert evidence.is_relative_to(root/'out/network-recovery')
restore=evidence/'restore.flag';events=evidence/'relay-events.jsonl';cut=threading.Event();lock=threading.Lock()
def log(kind,**values):
 with lock:
  with events.open('a',encoding='utf-8') as f:f.write(json.dumps({'event':kind,'at':time.time(),**values})+'\n')
class Handler(socketserver.BaseRequestHandler):
 def handle(self):
  upstream=None
  try:
   self.request.settimeout(15);header=b''
   while b'\r\n\r\n' not in header and len(header)<8192:
    chunk=self.request.recv(1)
    if not chunk:return
    header+=chunk
   parts=header.split(b'\r\n',1)[0].split()
   if len(parts)!=3 or parts[0]!=b'CONNECT' or parts[1].lower()!=b'github.com:443':
    self.request.sendall(b'HTTP/1.1 403 Forbidden\r\n\r\n');log('rejected_host');return
   if cut.is_set() and not restore.exists():
    self.request.sendall(b'HTTP/1.1 503 Test outage\r\n\r\n');log('reconnect_blocked');return
   upstream=socket.create_connection(('github.com',443),timeout=15);upstream.setblocking(False);self.request.setblocking(False)
   self.request.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n');received=0;sent=0;log('connected',restored=restore.exists())
   while True:
    if cut.is_set() and not restore.exists():return
    ready,_,_=select.select([self.request,upstream],[],[],.1)
    for source in ready:
     try:data=source.recv(32768)
     except BlockingIOError:continue
     if not data:log('closed',upstreamBytes=received,downstreamBytes=sent);return
     target=self.request if source is upstream else upstream
     target.setblocking(True);target.sendall(data);target.setblocking(False)
     if source is upstream:
      received+=len(data)
      if received>=config.get('cutAfterBytes',65536) and not restore.exists():
       cut.set();log('transfer_cut',upstreamBytes=received,downstreamBytes=sent);return
     else:sent+=len(data)
  except (OSError,ValueError) as e:log('socket_end',errorType=type(e).__name__)
  finally:
   if upstream:
    try:upstream.shutdown(socket.SHUT_RDWR)
    except OSError:pass
    upstream.close()
   try:self.request.shutdown(socket.SHUT_RDWR)
   except OSError:pass
class Server(socketserver.ThreadingTCPServer):
 allow_reuse_address=True
 daemon_threads=True
with Server(('127.0.0.1',0),Handler) as server:
 (evidence/'relay-ready.json').write_text(json.dumps({'host':'127.0.0.1','port':server.server_address[1],'target':'github.com:443'}),encoding='utf-8')
 log('listening',port=server.server_address[1]);server.serve_forever(poll_interval=.1)
