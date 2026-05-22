"""
run_dashboard.py — Local Dashboard Server and Pipeline Runner
============================================================
Mutual Fund Analysis Dashboard

This script starts a lightweight local web server to host the mutual fund 
dashboard. It prevents browser caching, handles local CORS naturally,
and exposes a POST endpoint to trigger the data pipeline.

Usage:
    python run_dashboard.py
"""

import os
import sys
import subprocess
import webbrowser
import http.server
import socketserver

PORT = 8000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Disable caching completely to ensure data refresh is seen instantly
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        # Add basic CORS headers for safety
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def do_POST(self):
        # Endpoint to trigger run_pipeline.py
        if self.path == '/run-pipeline':
            print("\n[Server] Triggering run_pipeline.py pipeline refresh...")
            
            try:
                # Use same Python interpreter context
                python_bin = sys.executable
                pipeline_script = os.path.join(BASE_DIR, "run_pipeline.py")
                
                # Execute pipeline synchronously
                result = subprocess.run(
                    [python_bin, pipeline_script], 
                    capture_output=True, 
                    text=True, 
                    cwd=BASE_DIR
                )
                
                if result.returncode == 0:
                    print("[Server] Pipeline completed successfully!")
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"status":"success","message":"Data pipeline executed successfully"}')
                else:
                    print(f"[Server] Pipeline failed with exit code: {result.returncode}")
                    print(f"Error output:\n{result.stderr}\n{result.stdout}")
                    self.send_response(500)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    response_msg = f'{{"status":"error","message":"Pipeline failed","exit_code":{result.returncode}}}'
                    self.wfile.write(response_msg.encode('utf-8'))
                    
            except Exception as e:
                print(f"[Server] Error running pipeline: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response_msg = f'{{"status":"error","message":"{str(e)}"}}'
                self.wfile.write(response_msg.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def main():
    # Make sure server runs in the script's directory
    os.chdir(BASE_DIR)
    
    # Allow port reuse to avoid 'address already in use' errors on fast restarts
    socketserver.TCPServer.allow_reuse_address = True
    
    with socketserver.TCPServer(("", PORT), DashboardRequestHandler) as httpd:
        print("=" * 70)
        print(f"  MUTUAL FUNDS DASHBOARD SERVER RUNNING")
        print(f"  Url                   : http://localhost:{PORT}")
        print(f"  Local Workspace       : {BASE_DIR}")
        print("=" * 70)
        
        # Open in default browser automatically
        webbrowser.open(f"http://localhost:{PORT}")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[Server] Shutting down web server. Goodbye!")

if __name__ == "__main__":
    main()
