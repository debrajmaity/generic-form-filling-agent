#!/usr/bin/env python3
"""
Puppeteer Server Manager - Manages Node.js Puppeteer server lifecycle from Python
"""

import asyncio
import subprocess
import os
import time
import aiohttp
import json
from typing import Optional, Dict, Any
from pathlib import Path


class PuppeteerServerManager:
    """Manages Puppeteer Node.js server lifecycle"""
    
    def __init__(self, 
                 server_path: str = None,
                 server_port: int = 3000,
                 cdp_port: int = 9222,
                 auto_install: bool = True):
        """
        Initialize Puppeteer server manager
        
        Args:
            server_path: Path to puppeteer-server directory
            server_port: Port for Puppeteer REST API
            cdp_port: Port for Chrome DevTools Protocol
            auto_install: Auto-install npm dependencies if needed
        """
        self.server_path = server_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
            "puppeteer-server"
        )
        self.server_port = server_port
        self.cdp_port = cdp_port
        self.auto_install = auto_install
        self.process: Optional[subprocess.Popen] = None
        self.server_url = f"http://localhost:{server_port}"
        self.cdp_url = f"http://localhost:{cdp_port}"
        
    async def is_server_running(self) -> bool:
        """Check if Puppeteer server is running"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.server_url}/status", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        status = await resp.json()
                        # Server is running if it responds, regardless of browser status
                        return True
        except Exception as e:
            # Server is not reachable
            return False
        return False
    
    async def get_server_status(self) -> Dict[str, Any]:
        """Get detailed server status"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.server_url}/status") as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}
        return {"status": "not_running"}
    
    async def ensure_dependencies(self) -> bool:
        """Ensure npm dependencies are installed"""
        package_json = os.path.join(self.server_path, "package.json")
        node_modules = os.path.join(self.server_path, "node_modules")
        
        if not os.path.exists(package_json):
            print(f"❌ No package.json found at {self.server_path}")
            return False
        
        if not os.path.exists(node_modules) and self.auto_install:
            print("📦 Installing npm dependencies...")
            try:
                result = subprocess.run(
                    ["npm", "install"],
                    cwd=self.server_path,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    print("✅ Dependencies installed successfully")
                    return True
                else:
                    print(f"❌ Failed to install dependencies: {result.stderr}")
                    return False
            except Exception as e:
                print(f"❌ Error installing dependencies: {e}")
                return False
        
        return os.path.exists(node_modules)
    
    async def start_server(self, headless: bool = False) -> Dict[str, Any]:
        """Start the Puppeteer server"""
        
        # Check if already running
        if await self.is_server_running():
            status = await self.get_server_status()
            print(f"✅ Puppeteer server already running")
            return {
                "success": True,
                "message": "Server already running",
                "cdp_url": self.cdp_url,
                "ws_endpoint": status.get('wsEndpoint')
            }
        
        # Ensure dependencies
        if not await self.ensure_dependencies():
            return {
                "success": False,
                "message": "Failed to ensure dependencies",
                "error": "npm dependencies not installed"
            }
        
        # Prepare environment
        env = os.environ.copy()
        env['PORT'] = str(self.server_port)
        env['CDP_PORT'] = str(self.cdp_port)
        env['HEADLESS'] = 'true' if headless else 'false'
        
        # Start server process
        try:
            print(f"🚀 Starting Puppeteer server on port {self.server_port}...")
            
            # Use basic server.js for now
            server_file = "server.js"
            
            # Check if node is available
            node_check = subprocess.run(["which", "node"], capture_output=True, text=True)
            if node_check.returncode != 0:
                return {
                    "success": False,
                    "message": "Node.js not found",
                    "error": "Please install Node.js to run Puppeteer server"
                }
            
            print(f"📁 Server path: {self.server_path}")
            print(f"📄 Server file: {server_file}")
            
            self.process = subprocess.Popen(
                ["node", server_file],
                cwd=self.server_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            print(f"🔄 Started process with PID: {self.process.pid}")
            
            # Wait for server to start
            max_retries = 30
            for i in range(max_retries):
                await asyncio.sleep(0.5)
                
                # Check if process is still running
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate()
                    print(f"❌ Process died early")
                    print(f"STDOUT: {stdout}")
                    print(f"STDERR: {stderr}")
                    return {
                        "success": False,
                        "message": "Server process died",
                        "error": stderr or stdout
                    }
                
                if await self.is_server_running():
                    print(f"✅ Puppeteer server started successfully")
                    
                    # Get server status
                    status = await self.get_server_status()
                    
                    # Ensure browser is started
                    if status.get('status') != 'running':
                        print(f"🌐 Starting browser...")
                        browser_started = await self._start_browser()
                        if browser_started:
                            # Get updated status
                            status = await self.get_server_status()
                    
                    return {
                        "success": True,
                        "message": "Server started successfully",
                        "cdp_url": self.cdp_url,
                        "ws_endpoint": status.get('wsEndpoint'),
                        "pid": self.process.pid
                    }
                
                # Check if process failed
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate()
                    return {
                        "success": False,
                        "message": "Server process failed to start",
                        "error": stderr or stdout
                    }
            
            return {
                "success": False,
                "message": "Server failed to start within timeout",
                "error": "Timeout waiting for server"
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": "Failed to start server",
                "error": str(e)
            }
    
    async def _start_browser(self) -> bool:
        """Start browser via Puppeteer server API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.server_url}/browser/start") as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        print(f"🌐 Browser started: {result.get('message')}")
                        return True
        except Exception as e:
            print(f"❌ Failed to start browser: {e}")
        return False
    
    async def stop_server(self) -> Dict[str, Any]:
        """Stop the Puppeteer server"""
        
        # First try graceful shutdown via API
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.server_url}/browser/stop") as resp:
                    if resp.status == 200:
                        print("🛑 Browser stopped via API")
        except:
            pass
        
        # Stop the process
        if self.process:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                
                print("✅ Puppeteer server stopped")
                self.process = None
                
                return {
                    "success": True,
                    "message": "Server stopped successfully"
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": "Failed to stop server",
                    "error": str(e)
                }
        
        return {
            "success": True,
            "message": "Server was not running"
        }
    
    async def restart_server(self, headless: bool = False) -> Dict[str, Any]:
        """Restart the Puppeteer server"""
        print("🔄 Restarting Puppeteer server...")
        
        # Stop if running
        await self.stop_server()
        
        # Wait a moment
        await asyncio.sleep(1)
        
        # Start again
        return await self.start_server(headless)
    
    def __del__(self):
        """Cleanup on deletion"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                try:
                    self.process.kill()
                except:
                    pass


# Example usage
async def test_manager():
    """Test the Puppeteer server manager"""
    manager = PuppeteerServerManager()
    
    # Start server
    result = await manager.start_server(headless=False)
    print(f"Start result: {result}")
    
    if result['success']:
        # Check status
        status = await manager.get_server_status()
        print(f"Server status: {status}")
        
        # Wait a bit
        await asyncio.sleep(5)
        
        # Stop server
        stop_result = await manager.stop_server()
        print(f"Stop result: {stop_result}")


if __name__ == "__main__":
    asyncio.run(test_manager())