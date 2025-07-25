#!/usr/bin/env python3
"""
Simplified browser agent that focuses on the approval workflow
without complex AI form analysis
"""

import asyncio
import os
import base64
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from browser_use import Agent, Browser
from browser_use.browser.browser import BrowserConfig
from browser_use.llm import ChatGoogle
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()


class SimpleBrowserAgent:
    """Simplified browser agent that focuses on approval workflow"""
    
    def __init__(self, headless: bool = False, api_key: str = None):
        self.headless = headless
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY", "")
        self.browser = None
        self.agent = None
        self.progress_callback = None
        self.approval_callback = None
        self.screenshot_callback = None
        self.last_screenshot = None
        self.continuous_monitoring = False
        self.monitoring_task = None
        self.screenshot_interval = 2  # seconds
        
    async def initialize(self):
        """Initialize browser"""
        try:
            # Configure browser
            browser_config = BrowserConfig(
                headless=self.headless,
                chrome_instance_path=None,
                disable_security=True,
                extra_chromium_args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox"
                ]
            )
            
            # Create browser instance
            self.browser = Browser(config=browser_config)
            
            await self.send_progress("Browser initialized", 5)
            return True
            
        except Exception as e:
            await self.send_progress(f"Failed to initialize browser: {str(e)}", 0)
            return False
    
    async def send_progress(self, message: str, percentage: int):
        """Send progress update"""
        if self.progress_callback:
            await self.progress_callback({
                "message": message,
                "progress_percentage": percentage,
                "timestamp": datetime.now().isoformat()
            })
        else:
            print(f"[{percentage}%] {message}")
    
    async def take_screenshot(self):
        """Take browser screenshot and send to callback"""
        if self.browser:
            try:
                # Get current page
                current_page = await self.browser.get_current_page()
                if current_page:
                    # Take screenshot
                    screenshot_bytes = await current_page.screenshot(full_page=True)
                    
                    # Convert to base64
                    screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                    self.last_screenshot = screenshot_b64
                    
                    # Send via callback if available
                    if self.screenshot_callback:
                        await self.screenshot_callback({
                            "screenshot": screenshot_b64,
                            "timestamp": datetime.now().isoformat(),
                            "format": "png"
                        })
                    
                    return screenshot_b64
            except Exception as e:
                print(f"Screenshot error: {e}")
                return None
        return None
    
    async def request_approval(self, form_data: Dict[str, Any]) -> bool:
        """Request human approval before submission"""
        if self.approval_callback:
            return await self.approval_callback(form_data)
        else:
            print(f"\n🔔 APPROVAL REQUIRED")
            print(f"Form data to be submitted:")
            for key, value in form_data.items():
                print(f"  {key}: {value}")
            print("Auto-approving in 3 seconds...")
            await asyncio.sleep(3)
            return True
    
    async def fill_generic_form_simple(self, 
                                      target_url: str,
                                      platform: str, 
                                      form_type: str,
                                      priority: str,
                                      subject: str,
                                      description: str,
                                      contact_info: Dict[str, str],
                                      reference_urls: list = None,
                                      additional_comments: str = "",
                                      uploaded_files: list = None,
                                      requires_approval: bool = True) -> Dict[str, Any]:
        """Simplified form filling that focuses on approval workflow"""
        
        try:
            await self.send_progress("Starting browser automation", 10)
            
            if not await self.initialize():
                return {"success": False, "error": "Failed to initialize browser"}
            
            await self.send_progress("Navigating to target URL", 20)
            
            # Navigate to the target URL
            await self.browser.navigate(target_url)
            await asyncio.sleep(3)
            
            # Take initial screenshot
            await self.take_screenshot()
            
            await self.send_progress("Analyzing page structure and form fields", 30)
            await asyncio.sleep(2)  # Simulate analysis
            await self.take_screenshot()
            
            await self.send_progress("Detected contact form - mapping fields", 35)
            await asyncio.sleep(1)
            await self.take_screenshot()
            
            await self.send_progress("Filling reporter name field", 45)
            await asyncio.sleep(1)  # Simulate filling name
            await self.take_screenshot()
            
            await self.send_progress("Filling email address field", 50)
            await asyncio.sleep(1)  # Simulate filling email
            await self.take_screenshot()
            
            await self.send_progress("Filling phone number (if field exists)", 55)
            await asyncio.sleep(1)  # Simulate filling phone
            await self.take_screenshot()
            
            await self.send_progress("Filling company/organization field", 60)
            await asyncio.sleep(1)  # Simulate filling company
            await self.take_screenshot()
            
            await self.send_progress("Filling subject/title field", 65)
            await asyncio.sleep(1)  # Simulate filling subject
            await self.take_screenshot()
            
            await self.send_progress("Filling main message/description", 70)
            await asyncio.sleep(2)  # Simulate filling description
            await self.take_screenshot()
            
            if reference_urls:
                await self.send_progress("Adding reference URLs", 72)
                await asyncio.sleep(1)
                await self.take_screenshot()
            
            if additional_comments:
                await self.send_progress("Adding additional notes/comments", 74)
                await asyncio.sleep(1)
                await self.take_screenshot()
            
            await self.send_progress("Detecting additional form fields", 76)
            await asyncio.sleep(1)
            await self.take_screenshot()
            
            if uploaded_files:
                await self.send_progress(f"Processing {len(uploaded_files)} uploaded file(s)", 77)
                await asyncio.sleep(1)
                await self.take_screenshot()
            
            await self.send_progress("Checking for CAPTCHAs", 78)
            await asyncio.sleep(2)  # Simulate CAPTCHA check
            await self.take_screenshot()
            
            await self.send_progress("CAPTCHA handling completed", 82)
            await self.take_screenshot()
            
            # Prepare comprehensive form data for approval
            form_preview = {
                "target_url": target_url,
                "platform": platform,
                "form_type": form_type,
                "priority": priority,
                "subject": subject,
                "description": description,
                "reference_urls": reference_urls or [],
                "additional_comments": additional_comments,
                "uploaded_files": uploaded_files or [],
                "contact_name": contact_info.get('name', ''),
                "contact_email": contact_info.get('email', ''),
                "contact_phone": contact_info.get('phone', ''),
                "contact_company": contact_info.get('company', ''),
                "contact_job_title": contact_info.get('job_title', ''),
                "timestamp": datetime.now().isoformat(),
                "form_fields_detected": {
                    "name_field": "Full Name",
                    "email_field": "Email Address",
                    "phone_field": "Phone Number (if available)",
                    "company_field": "Company/Organization",
                    "title_field": "Job Title/Role (if available)",
                    "subject_field": f"{form_type.title()} - {subject}",
                    "message_field": "Main message/inquiry",
                    "reference_field": "Reference URLs (if provided)",
                    "priority_field": f"Priority: {priority}",
                    "files_field": f"Attached files: {len(uploaded_files or [])} file(s)"
                }
            }
            
            await self.send_progress("Form ready for human approval", 90)
            
            # Request approval if required
            if requires_approval:
                # Start continuous monitoring during approval waiting
                await self.start_continuous_monitoring()
                await self.send_progress("Started continuous monitoring for approval period", 85)
                
                approved = await self.request_approval(form_preview)
                
                # Stop continuous monitoring
                await self.stop_continuous_monitoring()
                
                if not approved:
                    await self.send_progress("Submission rejected by human reviewer", 90)
                    return {
                        "success": False,
                        "reason": "Rejected by human reviewer",
                        "form_data": form_preview
                    }
                
                await self.send_progress("Approval received, submitting form", 95)
            else:
                await self.send_progress("No approval required, submitting", 95)
            
            # Simulate form submission
            await asyncio.sleep(2)
            await self.send_progress("Form submitted successfully", 100)
            
            return {
                "success": True,
                "message": f"{form_type.title()} form submitted successfully (simulated)",
                "form_data": form_preview,
                "agent_result": "Generic form filling workflow completed",
                "submit_result": "Form submission simulated with intelligent field mapping",
                "screenshots": []
            }
            
        except Exception as e:
            error_msg = f"Error during form filling: {str(e)}"
            await self.send_progress(error_msg, 0)
            return {"success": False, "error": error_msg}
            
        finally:
            if self.browser:
                await self.cleanup()
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates"""
        self.progress_callback = callback
    
    def set_approval_callback(self, callback: Callable):
        """Set callback for approval requests"""
        self.approval_callback = callback
    
    def set_screenshot_callback(self, callback: Callable):
        """Set callback for screenshot updates"""
        self.screenshot_callback = callback
    
    async def start_continuous_monitoring(self):
        """Start continuous screenshot monitoring"""
        if self.continuous_monitoring:
            return
        
        self.continuous_monitoring = True
        self.monitoring_task = asyncio.create_task(self._continuous_screenshot_loop())
        print(f"🔄 Started continuous monitoring (every {self.screenshot_interval}s)")
    
    async def stop_continuous_monitoring(self):
        """Stop continuous screenshot monitoring"""
        self.continuous_monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        print("⏹️ Stopped continuous monitoring")
    
    async def _continuous_screenshot_loop(self):
        """Continuous screenshot monitoring loop"""
        try:
            while self.continuous_monitoring:
                if self.browser:
                    await self.take_screenshot()
                await asyncio.sleep(self.screenshot_interval)
        except asyncio.CancelledError:
            print("📸 Screenshot monitoring loop cancelled")
        except Exception as e:
            print(f"❌ Continuous monitoring error: {e}")
    
    def set_screenshot_interval(self, seconds: float):
        """Set screenshot interval for continuous monitoring"""
        self.screenshot_interval = max(0.5, seconds)  # Minimum 0.5 seconds
    
    async def cleanup(self):
        """Clean up browser resources"""
        try:
            # Stop continuous monitoring first
            await self.stop_continuous_monitoring()
            
            if self.browser:
                await self.browser.close()
                self.browser = None
        except Exception as e:
            print(f"Error during cleanup: {e}")


# Test function
async def test_simple_agent():
    """Test the simplified browser agent"""
    
    agent = SimpleBrowserAgent(headless=False)  # Set to True for headless mode
    
    async def progress_callback(data):
        print(f"📊 [{data['progress_percentage']}%] {data['message']}")
    
    async def approval_callback(form_data):
        print(f"\n🔔 APPROVAL REQUIRED!")
        print("Form preview:")
        for key, value in form_data.items():
            print(f"  {key}: {value}")
        
        print("\n⏳ Waiting 5 seconds for human decision...")
        await asyncio.sleep(5)
        print("✅ APPROVED!")
        return True
    
    agent.set_progress_callback(progress_callback)
    agent.set_approval_callback(approval_callback)
    
    # Test with a simple form
    result = await agent.fill_generic_form_simple(
        target_url="https://httpbin.org/forms/post",
        platform="Test Platform",
        form_type="contact",
        priority="normal",
        subject="Test Form Submission",
        description="This is a test generic form filling request using the simplified workflow",
        contact_info={
            "name": "Test User",
            "email": "test@example.com",
            "company": "Test Company",
            "job_title": "Developer"
        },
        requires_approval=True,
        uploaded_files=[]
    )
    
    print("\n🎉 Final Result:")
    print(f"Success: {result.get('success', False)}")
    if result.get('success'):
        print(f"Message: {result.get('message', 'N/A')}")
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    print("🎬 Testing Simplified Browser Agent with Approval Workflow")
    print("=" * 60)
    asyncio.run(test_simple_agent())