"""Serve the citizen portal on http://localhost:5174 (it talks to the API on :8000)."""
import http.server
import os
import socketserver

os.chdir(os.path.dirname(os.path.abspath(__file__)))
socketserver.TCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", 5174), http.server.SimpleHTTPRequestHandler) as srv:
    print("Citizen portal: http://localhost:5174")
    srv.serve_forever()
