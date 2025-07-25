#!/usr/bin/env python3
"""
Test Puppeteer server directly to see console output
"""

import subprocess
import time
import requests
import os

def test_server_direct():
    """Test server with direct subprocess to see output"""
    print("🧪 Testing Puppeteer Server Directly")
    print("=" * 60)
    
    server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puppeteer-server")
    
    # Start server process
    print("Starting server process...")
    process = subprocess.Popen(
        ["node", "server.js"],
        cwd=server_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Read output for a few seconds
    print("\nServer output:")
    print("-" * 40)
    
    start_time = time.time()
    while time.time() - start_time < 10:  # Run for 10 seconds
        line = process.stdout.readline()
        if line:
            print(f"[SERVER] {line.strip()}")
        
        # Check if server is ready
        if "Puppeteer server running" in line:
            time.sleep(2)  # Give it time to start browser
            
            # Check status
            try:
                response = requests.get("http://localhost:3000/status")
                print(f"\n📊 Server status: {response.json()}")
            except Exception as e:
                print(f"❌ Error checking status: {e}")
            
        # Check if process died
        if process.poll() is not None:
            print(f"❌ Process died with code: {process.returncode}")
            break
    
    # Clean up
    print("\nStopping server...")
    process.terminate()
    process.wait()
    print("✅ Server stopped")


if __name__ == "__main__":
    test_server_direct()