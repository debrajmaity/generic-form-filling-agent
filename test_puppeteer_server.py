#!/usr/bin/env python3
"""
Test script to debug Puppeteer server startup issues
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.utils.puppeteer_server_manager import PuppeteerServerManager


async def test_server():
    """Test Puppeteer server startup"""
    print("🧪 Testing Puppeteer Server Manager")
    print("=" * 60)
    
    manager = PuppeteerServerManager()
    
    print(f"\n1. Server configuration:")
    print(f"   Server path: {manager.server_path}")
    print(f"   Server URL: {manager.server_url}")
    print(f"   CDP URL: {manager.cdp_url}")
    
    # Check if server path exists
    if not os.path.exists(manager.server_path):
        print(f"❌ Server path does not exist: {manager.server_path}")
        return
    
    # Check if package.json exists
    package_json = os.path.join(manager.server_path, "package.json")
    if not os.path.exists(package_json):
        print(f"❌ package.json not found at: {package_json}")
        return
    else:
        print(f"✅ Found package.json")
    
    # Check if node_modules exists
    node_modules = os.path.join(manager.server_path, "node_modules")
    if not os.path.exists(node_modules):
        print(f"⚠️  node_modules not found, will need to install dependencies")
    else:
        print(f"✅ Found node_modules")
    
    # Check if server.js exists
    server_js = os.path.join(manager.server_path, "server.js")
    if not os.path.exists(server_js):
        print(f"❌ server.js not found at: {server_js}")
        return
    else:
        print(f"✅ Found server.js")
    
    print(f"\n2. Checking if server is already running...")
    is_running = await manager.is_server_running()
    print(f"   Server running: {is_running}")
    
    if is_running:
        status = await manager.get_server_status()
        print(f"   Server status: {status}")
        return
    
    print(f"\n3. Starting Puppeteer server...")
    result = await manager.start_server(headless=False)
    
    print(f"\n4. Start result:")
    print(f"   Success: {result['success']}")
    print(f"   Message: {result.get('message', 'N/A')}")
    if result.get('error'):
        print(f"   Error: {result['error']}")
    if result.get('cdp_url'):
        print(f"   CDP URL: {result['cdp_url']}")
    if result.get('ws_endpoint'):
        print(f"   WebSocket: {result['ws_endpoint']}")
    
    if result['success']:
        print(f"\n5. Checking server status...")
        status = await manager.get_server_status()
        print(f"   Status: {status}")
        
        print(f"\n6. Waiting 5 seconds...")
        await asyncio.sleep(5)
        
        print(f"\n7. Stopping server...")
        stop_result = await manager.stop_server()
        print(f"   Stop result: {stop_result}")


if __name__ == "__main__":
    asyncio.run(test_server())