#!/usr/bin/env python3
"""
Test script demonstrating managed Puppeteer server lifecycle
The Python agent automatically starts and stops the Node.js Puppeteer server
"""

import requests
import json
import time
import asyncio
import websockets

async def monitor_job(job_id):
    """Monitor job progress via WebSocket"""
    uri = f"ws://localhost:8002/ws/job/{job_id}"
    
    print(f"📡 Connecting to WebSocket for job {job_id}")
    
    try:
        async with websockets.connect(uri) as websocket:
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    print(f"[{data.get('type')}] {data.get('message')}")
                    
                    if data.get('type') == 'status_change' and data.get('data', {}).get('status') in ['completed', 'failed']:
                        break
                        
                except websockets.exceptions.ConnectionClosed:
                    print("WebSocket connection closed")
                    break
                except Exception as e:
                    print(f"Error: {e}")
                    break
    except Exception as e:
        print(f"Failed to connect to WebSocket: {e}")

def test_managed_puppeteer():
    """Test form submission with managed Puppeteer server"""
    
    # API endpoint
    url = "http://localhost:8002/api/v1/form/submit"
    
    # Test data with managed Puppeteer
    data = {
        "target_url": "https://httpbin.org/forms/post",
        "platform": "HTTPBin Test Form",
        "form_type": "contact",
        "priority": "high",
        "subject": "Testing Managed Puppeteer Server",
        "description": "The Python agent automatically manages the Node.js Puppeteer server lifecycle.",
        "reference_urls": ["https://example.com/managed"],
        "additional_comments": "No need to manually start Puppeteer server!",
        "contact_info": {
            "name": "Managed Puppeteer User",
            "email": "managed@example.com",
            "phone": "+1-555-AUTO",
            "company": "Auto Management Corp"
        },
        "require_human_approval": False,
        "headless": False,
        "browser_engine": "puppeteer",
        "manage_puppeteer_server": True  # This tells the agent to manage the server
    }
    
    print("🚀 Submitting form with MANAGED Puppeteer server...")
    print("   The Python agent will automatically:")
    print("   1. Start the Node.js Puppeteer server")
    print("   2. Launch Chrome browser")
    print("   3. Fill the form")
    print("   4. Stop everything when done")
    print("")
    print(f"Target URL: {data['target_url']}")
    print(f"Browser Engine: {data['browser_engine']}")
    print(f"Server Management: Automatic")
    
    try:
        # Submit the form
        response = requests.post(url, json=data)
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('job_id')
            print(f"\n✅ Job created successfully!")
            print(f"Job ID: {job_id}")
            print(f"Message: {result.get('message')}")
            
            # Monitor the job
            print("\n📊 Monitoring job progress...")
            asyncio.run(monitor_job(job_id))
            
            # Get final job status
            time.sleep(2)
            status_response = requests.get(f"http://localhost:8002/api/v1/jobs/{job_id}")
            if status_response.status_code == 200:
                final_status = status_response.json()
                print(f"\n📋 Final Job Status:")
                print(f"Status: {final_status.get('status')}")
                print(f"Progress: {final_status.get('progress_percentage')}%")
                
                if final_status.get('result'):
                    print(f"\n🎉 Result:")
                    result_data = final_status.get('result')
                    if isinstance(result_data, dict):
                        print(json.dumps(result_data, indent=2))
                    else:
                        print(result_data)
                    
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Error: {e}")

def test_external_puppeteer():
    """Test with external (non-managed) Puppeteer server"""
    
    print("\n" + "="*60)
    print("🔧 Testing with EXTERNAL Puppeteer server...")
    print("   Assuming Puppeteer server is already running on port 3000")
    
    # API endpoint
    url = "http://localhost:8002/api/v1/form/submit"
    
    # Test data with external Puppeteer
    data = {
        "target_url": "https://example.com",
        "platform": "Example Site",
        "form_type": "general",
        "priority": "normal",
        "subject": "Testing External Puppeteer",
        "description": "Using externally managed Puppeteer server",
        "contact_info": {
            "name": "External User",
            "email": "external@example.com"
        },
        "require_human_approval": False,
        "headless": False,
        "browser_engine": "puppeteer",
        "manage_puppeteer_server": False,  # Don't manage the server
        "cdp_url": "http://localhost:9222"  # External CDP endpoint
    }
    
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Job created: {result.get('job_id')}")
        else:
            print(f"❌ Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🧪 Testing Puppeteer Server Lifecycle Management")
    print("=" * 60)
    print("\n📝 This test demonstrates:")
    print("1. Automatic Puppeteer server management by Python agent")
    print("2. No need to manually start Node.js server")
    print("3. Clean shutdown after job completion")
    print("\n⚠️  Make sure the Live Browser server is running:")
    print("   bash scripts/start_live_browser.sh")
    print("\n")
    
    # Test managed server
    test_managed_puppeteer()
    
    # Optionally test external server
    # test_external_puppeteer()