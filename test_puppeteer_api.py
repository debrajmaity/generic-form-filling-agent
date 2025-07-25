#!/usr/bin/env python3
"""
Test script to submit a form using the Puppeteer browser engine via API
"""

import requests
import json
import time
import asyncio
import websockets

async def monitor_job(job_id):
    """Monitor job progress via WebSocket"""
    uri = f"ws://localhost:8002/ws/job/{job_id}"
    
    async with websockets.connect(uri) as websocket:
        print(f"Connected to WebSocket for job {job_id}")
        
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

def test_puppeteer_form_submission():
    """Test form submission with Puppeteer engine"""
    
    # API endpoint
    url = "http://localhost:8002/api/v1/form/submit"
    
    # Test data with Puppeteer engine
    data = {
        "target_url": "https://httpbin.org/forms/post",
        "platform": "HTTPBin Test Form",
        "form_type": "contact",
        "priority": "high",
        "subject": "Testing Puppeteer Browser Engine",
        "description": "This is a test of the Puppeteer browser engine with CDP integration for form filling.",
        "reference_urls": ["https://example.com/ref1", "https://example.com/ref2"],
        "additional_comments": "Testing browser-use with CDP connection",
        "contact_info": {
            "name": "Puppeteer Test User",
            "email": "puppeteer.test@example.com",
            "phone": "+1-555-0123",
            "company": "Puppeteer Test Corp",
            "job_title": "QA Engineer"
        },
        "require_human_approval": False,  # Auto-approve for testing
        "headless": False,  # Show browser
        "browser_engine": "puppeteer"  # Use Puppeteer engine
    }
    
    print("🚀 Submitting form with Puppeteer browser engine...")
    print(f"Target URL: {data['target_url']}")
    print(f"Browser Engine: {data['browser_engine']}")
    print(f"Headless: {data['headless']}")
    
    try:
        # Submit the form
        response = requests.post(url, json=data)
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('job_id')
            print(f"✅ Job created successfully!")
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
                    print(json.dumps(final_status.get('result'), indent=2))
                    
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🧪 Testing Puppeteer Browser Engine via API")
    print("=" * 60)
    test_puppeteer_form_submission()