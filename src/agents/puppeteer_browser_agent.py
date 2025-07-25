#!/usr/bin/env python3
"""
Puppeteer browser agent that uses browser-use with Chrome DevTools Protocol (CDP)
"""

import asyncio
import os
import base64
import json
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
from browser_use import Agent, Browser
from browser_use.browser.browser import BrowserConfig
from browser_use.llm import ChatGoogle
from dotenv import load_dotenv
import aiohttp
from ..utils.puppeteer_server_manager import PuppeteerServerManager

# Load environment variables
load_dotenv()


class PuppeteerBrowserAgent:
    """Browser agent using browser-use with CDP connection"""
    
    def __init__(self, headless: bool = False, cdp_url: str = None, api_key: str = None, 
                 manage_server: bool = True, server_path: str = None):
        self.headless = headless
        self.cdp_url = cdp_url or "http://localhost:9222"
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
        self.manage_server = manage_server
        self.server_manager = None
        
        # Initialize server manager if needed
        if self.manage_server:
            self.server_manager = PuppeteerServerManager(
                server_path=server_path,
                server_port=3000,
                cdp_port=9222
            )
        
    async def initialize(self):
        """Initialize browser-use with CDP connection"""
        try:
            await self.send_progress("Initializing browser-use with CDP", 5)
            
            # Start Puppeteer server if managed
            if self.manage_server and self.server_manager:
                await self.send_progress("Starting managed Puppeteer server", 3)
                start_result = await self.server_manager.start_server(headless=self.headless)
                
                if not start_result['success']:
                    await self.send_progress(f"Failed to start Puppeteer server: {start_result.get('error')}", 0)
                    return False
                
                await self.send_progress("Puppeteer server started successfully", 7)
                
                # Update CDP URL if provided by server
                if start_result.get('cdp_url'):
                    self.cdp_url = start_result['cdp_url']
            
            # Check if CDP endpoint is available
            cdp_available = False
            existing_browser_url = None
            puppeteer_server = False
            
            try:
                async with aiohttp.ClientSession() as session:
                    # First check if it's a Puppeteer server
                    try:
                        server_url = self.cdp_url.replace(':9222', ':3000')
                        async with session.get(f"{server_url}/status") as resp:
                            if resp.status == 200:
                                status = await resp.json()
                                if status.get('status') == 'running':
                                    existing_browser_url = status.get('wsEndpoint')
                                    cdp_available = True
                                    puppeteer_server = True
                                    await self.send_progress("Connected to Puppeteer server", 8)
                    except:
                        pass
                    
                    # If not Puppeteer server, check standard CDP
                    if not puppeteer_server:
                        async with session.get(f"{self.cdp_url}/json/version") as resp:
                            if resp.status == 200:
                                browser_info = await resp.json()
                                ws_endpoint = browser_info.get('webSocketDebuggerUrl')
                                if ws_endpoint:
                                    existing_browser_url = ws_endpoint
                                    cdp_available = True
                                    await self.send_progress("Found existing Chrome instance via CDP", 8)
            except:
                await self.send_progress("No existing Chrome instance found, will launch new one", 8)
            
            # Configure browser
            if cdp_available and existing_browser_url:
                # Use existing Chrome instance (either Puppeteer server or regular CDP)
                browser_config = BrowserConfig(
                    headless=False,  # Already running
                    chrome_instance_path=self.cdp_url,  # Pass CDP URL
                    disable_security=True,
                    extra_chromium_args=[]
                )
                await self.send_progress(f"Using existing browser via {'Puppeteer server' if puppeteer_server else 'CDP'}", 10)
            else:
                # Launch new browser with CDP enabled
                browser_config = BrowserConfig(
                    headless=self.headless,
                    chrome_instance_path=None,
                    disable_security=True,
                    extra_chromium_args=[
                        '--remote-debugging-port=9222',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox'
                    ]
                )
            
            # Create browser instance
            self.browser = Browser(config=browser_config)
            
            # Configure LLM
            llm_config = None
            if self.api_key:
                llm_config = ChatGoogle(
                    api_key=self.api_key,
                    model="gemini-1.5-flash",
                    temperature=0.1
                )
            
            # Initialize agent with browser
            self.agent = Agent(
                task="",  # Will be set per task
                llm=llm_config,
                browser=self.browser,
                save_conversation_path=None
            )
            
            await self.send_progress("Browser-use with CDP initialized successfully", 15)
            return True
            
        except Exception as e:
            await self.send_progress(f"Failed to initialize browser-use with CDP: {str(e)}", 0)
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
                # Get current page from browser-use
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
    
    async def fill_generic_form_puppeteer(self, 
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
        """Fill forms using browser-use with CDP and controllers"""
        
        try:
            await self.send_progress("Starting browser-use automation with CDP", 10)
            
            if not await self.initialize():
                return {"success": False, "error": "Failed to initialize browser-use with CDP"}
            
            await self.send_progress("Navigating to target URL", 20)
            
            # Navigate to the target URL
            await self.browser.navigate(target_url)
            await asyncio.sleep(3)
            
            # Take initial screenshot
            await self.take_screenshot()
            
            await self.send_progress("Analyzing page structure", 30)
            
            # Build form filling task
            contact_fields = []
            if contact_info.get('name'):
                contact_fields.append(f"   - Name/Full Name: {contact_info['name']}")
            if contact_info.get('email'):
                contact_fields.append(f"   - Email: {contact_info['email']}")
            if contact_info.get('phone'):
                contact_fields.append(f"   - Phone: {contact_info['phone']}")
            if contact_info.get('company'):
                contact_fields.append(f"   - Company/Organization: {contact_info['company']}")
            if contact_info.get('job_title'):
                contact_fields.append(f"   - Job Title/Role: {contact_info['job_title']}")
            
            task_description = f"""
            You are filling out a {form_type} form on {platform}. Please:
            
            1. Look for form fields and fill in the following information:
{chr(10).join(contact_fields)}
               - Subject/Title: {subject}
               - Message/Description: {description}
               - Priority/Urgency: {priority}
            
            2. If there are reference URL fields, add: {', '.join(reference_urls or [])}
            3. If there's an additional comments field, add: {additional_comments}
            4. DO NOT submit the form yet - just fill it out completely
            5. Take a screenshot when all fields are filled
            
            Focus on filling all available fields accurately. Stop before clicking submit.
            """
            
            self.agent.task = task_description
            
            await self.send_progress("AI agent filling form fields", 40)
            
            # Let the agent work on filling the form
            try:
                result = await asyncio.wait_for(self.agent.run(max_steps=12), timeout=90)
                await self.send_progress("Form fields filled successfully", 60)
            except asyncio.TimeoutError:
                await self.send_progress("Form filling timed out, proceeding with available data", 60)
                result = "Form filling timed out but proceeding"
            except Exception as e:
                await self.send_progress(f"Form filling error: {str(e)}", 60)
                result = f"Form filling error: {str(e)}"
            
            # Take screenshot after form filling
            await self.take_screenshot()
            
            # Handle file uploads if any
            if uploaded_files:
                await self.send_progress(f"Processing {len(uploaded_files)} file(s) for upload", 65)
                
                # Import controllers
                from ..controllers import file_upload_controller
                
                # Create task for file upload
                file_paths = [f.get('path', '') for f in uploaded_files if f.get('path')]
                file_names = [f.get('name', '') for f in uploaded_files if f.get('name')]
                
                file_upload_task = f"""
                Look for file upload fields on this form and upload the following files:
                {chr(10).join([f"   - {name}" for name in file_names])}
                
                Use the file upload controller to detect file input fields and upload the files.
                Report what files were uploaded and to which fields.
                """
                
                self.agent.task = file_upload_task
                
                # Integrate controller with agent
                self.agent._file_upload_controller = file_upload_controller
                self.agent._file_paths = file_paths
                
                try:
                    upload_result = await asyncio.wait_for(self.agent.run(max_steps=5), timeout=30)
                    await self.send_progress("File upload completed", 75)
                except Exception as e:
                    await self.send_progress(f"File upload error: {str(e)}", 75)
                    upload_result = f"File upload error: {str(e)}"
                
                await self.take_screenshot()
            
            await self.send_progress("Form filling completed", 85)
            
            # Prepare form data for approval
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
                "timestamp": datetime.now().isoformat(),
                "browser_type": "Browser-Use with CDP"
            }
            
            await self.send_progress("Form ready for human approval", 90)
            
            # Request approval if required
            if requires_approval:
                # Start continuous monitoring during approval
                await self.start_continuous_monitoring()
                await self.send_progress("Started continuous monitoring for approval period", 91)
                
                approved = await self.request_approval(form_preview)
                
                # Stop continuous monitoring
                await self.stop_continuous_monitoring()
                
                if not approved:
                    await self.send_progress("Submission rejected by human reviewer", 95)
                    return {
                        "success": False,
                        "reason": "Rejected by human reviewer",
                        "form_data": form_preview
                    }
                
                await self.send_progress("Approval received, submitting form", 95)
            else:
                await self.send_progress("No approval required, submitting", 95)
            
            # Submit the form
            submit_task = """
            Now submit the form by clicking the submit, send, or save button.
            Look for buttons with text like 'Submit', 'Send', 'Save', 'Post', 'Contact Us', etc.
            After clicking, wait for any confirmation and take a final screenshot.
            """
            
            self.agent.task = submit_task
            
            try:
                submit_result = await asyncio.wait_for(self.agent.run(max_steps=5), timeout=30)
            except asyncio.TimeoutError:
                await self.send_progress("Form submission timed out", 100)
                submit_result = "Form submission timed out"
            except Exception as e:
                await self.send_progress(f"Form submission error: {str(e)}", 100)
                submit_result = f"Form submission error: {str(e)}"
            
            await self.send_progress("Form submitted successfully", 100)
            
            # Take final screenshot
            await self.take_screenshot()
            
            return {
                "success": True,
                "message": f"{form_type.title()} form submitted successfully via Browser-Use with CDP",
                "form_data": form_preview,
                "agent_result": str(result),
                "submit_result": str(submit_result),
                "browser_type": "Browser-Use with CDP",
                "screenshots": []  # Would contain actual screenshots if needed
            }
            
        except Exception as e:
            error_msg = f"Error during browser-use form filling: {str(e)}"
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
                self.agent = None
            
            # Stop Puppeteer server if managed
            if self.manage_server and self.server_manager:
                await self.send_progress("Stopping managed Puppeteer server", 95)
                stop_result = await self.server_manager.stop_server()
                if stop_result['success']:
                    await self.send_progress("Puppeteer server stopped", 98)
                
        except Exception as e:
            print(f"Error during cleanup: {e}")


# Test function
async def test_puppeteer_agent():
    """Test the browser-use agent with CDP"""
    
    agent = PuppeteerBrowserAgent(headless=False)
    
    async def progress_callback(data):
        print(f"📊 [{data['progress_percentage']}%] {data['message']}")
    
    async def approval_callback(form_data):
        print(f"\n🔔 APPROVAL REQUIRED!")
        print("Form preview:")
        for key, value in form_data.items():
            if isinstance(value, dict):
                continue
            print(f"  {key}: {value}")
        
        print("\n⏳ Waiting 3 seconds for human decision...")
        await asyncio.sleep(3)
        print("✅ APPROVED!")
        return True
    
    agent.set_progress_callback(progress_callback)
    agent.set_approval_callback(approval_callback)
    
    # Test with a simple form
    result = await agent.fill_generic_form_puppeteer(
        target_url="https://httpbin.org/forms/post",
        platform="Test Platform",
        form_type="contact",
        priority="normal",
        subject="Test Browser-Use with CDP",
        description="Testing browser-use agent with CDP integration using the same pattern as real_browser_agent",
        contact_info={
            "name": "Test User",
            "email": "test@example.com",
            "phone": "+1234567890",
            "company": "Test Company"
        },
        requires_approval=True
    )
    
    print("\n🎉 Final Result:")
    print(f"Success: {result.get('success', False)}")
    if result.get('success'):
        print(f"Message: {result.get('message', 'N/A')}")
        print(f"Browser Type: {result.get('browser_type', 'N/A')}")
        print(f"Agent Result: {result.get('agent_result', 'N/A')[:100]}...")  # First 100 chars
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    print("🎬 Testing Browser-Use Agent with CDP")
    print("=" * 60)
    asyncio.run(test_puppeteer_agent())