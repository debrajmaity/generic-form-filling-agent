#!/usr/bin/env python3
"""
Live Browser Agent - Main Entry Point
"""

import sys
import os

# Add src directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, 'src')
sys.path.insert(0, src_path)

# Import and run server
if __name__ == "__main__":
    from server.live_browser_server import app
    import uvicorn
    
    print("🚀 Starting Live Browser Agent Server...")
    print("📱 Dashboard: http://localhost:8002/dashboard")
    print("🔧 Health Check: http://localhost:8002/health")
    print()
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8002,
        reload=False,
        log_level="info"
    )