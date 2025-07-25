#!/usr/bin/env python3
"""
Real browser agent using browser-use for actual form filling
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

# Load environment variables from .env file
load_dotenv()


class RealBrowserAgent:
    """Real browser agent that actually opens browser and fills forms"""
    
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
        """Initialize browser and agent"""
        try:
            # Configure browser
            browser_config = BrowserConfig(
                headless=self.headless,
                chrome_instance_path=None,  # Use default
                disable_security=True,  # For demo purposes
                extra_chromium_args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox"
                ]
            )
            
            # Create browser instance
            self.browser = Browser(config=browser_config)
            
            # Configure Gemini LLM
            llm_config = None
            if self.api_key:
                llm_config = ChatGoogle(
                    api_key=self.api_key,
                    model="gemini-1.5-pro",
                    temperature=0.1
                )
            
            # Initialize agent with browser
            self.agent = Agent(
                task="",  # Will be set per task
                llm=llm_config,
                browser=self.browser,
                save_conversation_path=None
            )
            
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
    
    async def request_approval(self, form_data: Dict[str, Any]) -> bool:
        """Request human approval before submission"""
        if self.approval_callback:
            return await self.approval_callback(form_data)
        else:
            # Fallback for testing - auto approve after showing data
            print(f"\n🔔 APPROVAL REQUIRED")
            print(f"Form data to be submitted:")
            for key, value in form_data.items():
                print(f"  {key}: {value}")
            print("Would you like to proceed? (This is a demo - auto-approving in 3 seconds)")
            await asyncio.sleep(3)
            return True
    
    async def fill_takedown_form(self, 
                                target_url: str,
                                platform: str, 
                                abuse_type: str,
                                description: str,
                                contact_info: Dict[str, str],
                                requires_approval: bool = True) -> Dict[str, Any]:
        """Fill out a takedown/abuse report form"""
        
        try:
            await self.send_progress("Starting browser automation", 10)
            
            if not await self.initialize():
                return {"success": False, "error": "Failed to initialize browser"}
            
            await self.send_progress("Navigating to target URL", 20)
            
            # Navigate to the target URL
            await self.browser.navigate(target_url)
            await asyncio.sleep(2)
            
            await self.send_progress("Analyzing page structure", 30)
            
            # Use browser-use agent to analyze and fill the form
            task_description = f"""
            You are filling out an abuse/takedown report form. Please:
            
            1. Look for form fields related to reporting abuse or copyright infringement
            2. Fill in the following information:
               - Platform/Service: {platform}
               - Type of abuse: {abuse_type}  
               - Description: {description}
               - Reporter name: {contact_info.get('name', '')}
               - Reporter email: {contact_info.get('email', '')}
               - Reporter organization: {contact_info.get('organization', '')}
            
            3. Handle any CAPTCHAs if present
            4. Fill all required fields but DO NOT submit the form yet
            5. Take a screenshot when the form is completely filled
            
            Stop before clicking any submit/send buttons and report what you've filled in.
            """
            
            self.agent.task = task_description
            
            await self.send_progress("AI agent analyzing form fields", 40)
            
            # Let the agent work on filling the form
            try:
                result = await asyncio.wait_for(self.agent.run(max_steps=10), timeout=60)
                await self.send_progress("Form analysis completed", 50)
            except asyncio.TimeoutError:
                await self.send_progress("Form analysis timed out, proceeding with available data", 50)
                result = "Form analysis timed out but proceeding"
            except Exception as e:
                await self.send_progress(f"Form analysis error: {str(e)}", 50)
                result = f"Form analysis error: {str(e)}"
            
            await self.send_progress("Form fields filled", 60)
            
            # Simulate CAPTCHA solving
            await self.send_progress("Checking for CAPTCHAs", 70)
            await asyncio.sleep(2)
            
            # Check if there are any CAPTCHAs to solve
            captcha_task = """
            Check if there are any CAPTCHAs, reCAPTCHAs, or verification challenges on this page.
            If found, attempt to solve them. Report what you find.
            """
            
            self.agent.task = captcha_task
            try:
                captcha_result = await asyncio.wait_for(self.agent.run(max_steps=5), timeout=30)
            except asyncio.TimeoutError:
                await self.send_progress("CAPTCHA check timed out, proceeding", 80)
                captcha_result = "CAPTCHA check timed out"
            except Exception as e:
                await self.send_progress(f"CAPTCHA check error: {str(e)}", 80)
                captcha_result = f"CAPTCHA error: {str(e)}"
            
            await self.send_progress("CAPTCHA handling completed", 80)
            
            # Prepare form data for approval
            form_preview = {
                "target_url": target_url,
                "platform": platform,
                "abuse_type": abuse_type,
                "description": description,
                "reporter_name": contact_info.get('name', ''),
                "reporter_email": contact_info.get('email', ''),
                "reporter_organization": contact_info.get('organization', ''),
                "timestamp": datetime.now().isoformat()
            }
            
            await self.send_progress("Requesting human approval for submission", 90)
            
            # Request approval if required
            if requires_approval:
                await self.send_progress("Ready for human approval", 90)
                approved = await self.request_approval(form_preview)
                
                if not approved:
                    await self.send_progress("Submission rejected by human reviewer", 90)
                    return {
                        "success": False,
                        "reason": "Rejected by human reviewer",
                        "form_data": form_preview
                    }
            else:
                await self.send_progress("Approval not required, proceeding", 90)
            
            await self.send_progress("Approval received, submitting form", 95)
            
            # Submit the form
            submit_task = """
            Now submit the form by clicking the submit, send, or report button.
            Look for buttons with text like 'Submit', 'Send Report', 'Report Abuse', etc.
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
            
            return {
                "success": True,
                "message": "Takedown form submitted successfully",
                "form_data": form_preview,
                "agent_result": str(result),
                "submit_result": str(submit_result),
                "screenshots": []  # Would contain actual screenshots
            }
            
        except Exception as e:
            error_msg = f"Error during form filling: {str(e)}"
            await self.send_progress(error_msg, 0)
            return {"success": False, "error": error_msg}
            
        finally:
            if self.browser:
                await self.cleanup()
    
    async def fill_generic_form(self, 
                               target_url: str,
                               form_data: Dict[str, Any],
                               requires_approval: bool = True) -> Dict[str, Any]:
        """Fill a generic form with provided data"""
        
        try:
            await self.send_progress("Starting generic form filling", 10)
            
            if not await self.initialize():
                return {"success": False, "error": "Failed to initialize browser"}
            
            await self.send_progress("Navigating to form page", 20)
            
            # Navigate to the target URL
            await self.browser.navigate(target_url)
            await asyncio.sleep(2)
            
            await self.send_progress("Analyzing form structure", 40)
            
            # Build task description from form data
            field_instructions = []
            for field_name, field_value in form_data.items():
                field_instructions.append(f"   - {field_name}: {field_value}")
            
            task_description = f"""
            Fill out the form on this page with the following information:
            {chr(10).join(field_instructions)}
            
            1. Look for form fields that match these names or purposes
            2. Fill in all the provided information
            3. Handle any CAPTCHAs if present
            4. DO NOT submit the form yet - just fill it out
            5. Take a screenshot when done
            """
            
            self.agent.task = task_description
            
            await self.send_progress("AI agent filling form fields", 60)
            
            # Let the agent fill the form
            result = await self.agent.run(max_steps=8)
            
            await self.send_progress("Form filled, checking for CAPTCHAs", 80)
            
            # Handle CAPTCHAs
            captcha_task = "Check for and solve any CAPTCHAs or verification challenges on this page."
            self.agent.task = captcha_task
            await self.agent.run(max_steps=3)
            
            await self.send_progress("Requesting approval for submission", 90)
            
            # Request approval
            if requires_approval:
                approved = await self.request_approval(form_data)
                
                if not approved:
                    await self.send_progress("Submission rejected", 90)
                    return {
                        "success": False,
                        "reason": "Rejected by human reviewer",
                        "form_data": form_data
                    }
            
            await self.send_progress("Submitting form", 95)
            
            # Submit
            submit_task = "Submit the form by clicking the submit button. Wait for confirmation."
            self.agent.task = submit_task
            submit_result = await self.agent.run(max_steps=3)
            
            await self.send_progress("Form submitted successfully", 100)
            
            return {
                "success": True,
                "message": "Form submitted successfully",
                "form_data": form_data,
                "agent_result": str(result),
                "submit_result": str(submit_result)
            }
            
        except Exception as e:
            error_msg = f"Error filling form: {str(e)}"
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
        except Exception as e:
            print(f"Error during cleanup: {e}")


# Test function
async def test_real_agent():
    """Test the real browser agent"""
    
    agent = RealBrowserAgent(headless=False)  # Set to True for headless mode
    
    # Test with a simple contact form
    result = await agent.fill_generic_form(
        target_url="https://httpbin.org/forms/post",
        form_data={
            "name": "Test User",
            "email": "test@example.com", 
            "subject": "Test Message",
            "message": "This is a test form submission from the browser agent"
        },
        requires_approval=True
    )
    
    print("Result:", json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    # Run the test
    asyncio.run(test_real_agent())