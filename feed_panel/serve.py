"""Serve the feed panel on http://localhost:5175 (it talks to the API on :8000)."""
import http.server
import os
import socketserver

os.chdir(os.path.dirname(os.path.abspath(__file__)))
socketserver.TCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", 5175), http.server.SimpleHTTPRequestHandler) as srv:
    print("Feed panel: http://localhost:5175")
    srv.serve_forever()
