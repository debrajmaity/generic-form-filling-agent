#!/usr/bin/env python3
"""
Live browser server with real browser automation using browser-use
"""

import asyncio
import uvicorn
import json
import os
import uuid
import aiofiles
import shutil
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from typing import Dict, Any, List
from PIL import Image
import PyPDF2
from enum import Enum
from pydantic import BaseModel, Field
from dotenv import load_dotenv

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agents'))

from simple_browser_agent import SimpleBrowserAgent

# Load environment variables from .env file
load_dotenv()

# Job status enum
class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"

# Request models
class FormFillingRequest(BaseModel):
    target_url: str
    platform: str
    form_type: str = "contact"
    priority: str = "normal"
    subject: str = ""
    description: str
    reference_urls: List[str] = []
    additional_comments: str = ""
    uploaded_files: List[Dict[str, Any]] = []
    contact_info: Dict[str, Any] = {}
    require_human_approval: bool = True
    auto_submit_timeout_minutes: int = 0
    browser_mode: str = "normal"
    headless: bool = False  # Set to False to see browser activity

class HumanApprovalRequest(BaseModel):
    approved: bool
    reason: str = None
    analyst_name: str = None
    analyst_notes: str = None

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.job_connections: Dict[str, List[WebSocket]] = {}
        self.global_connections: List[WebSocket] = []

    async def connect_job(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        if job_id not in self.job_connections:
            self.job_connections[job_id] = []
        self.job_connections[job_id].append(websocket)

    async def connect_global(self, websocket: WebSocket):
        await websocket.accept()
        self.global_connections.append(websocket)

    def disconnect_job(self, websocket: WebSocket, job_id: str):
        if job_id in self.job_connections:
            self.job_connections[job_id].remove(websocket)

    def disconnect_global(self, websocket: WebSocket):
        if websocket in self.global_connections:
            self.global_connections.remove(websocket)
    
    async def broadcast_job_update(self, job_id: str, update_type: str, message: str, data: Dict = None):
        """Broadcast update to job-specific WebSocket connections"""
        if job_id in self.job_connections:
            update = {
                "type": "job_update",
                "job_id": job_id,
                "update_type": update_type,
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "data": data or {}
            }
            
            for connection in self.job_connections[job_id]:
                try:
                    await connection.send_text(json.dumps(update))
                except:
                    pass  # Connection might be closed
    
    async def broadcast_global_update(self, update_type: str, message: str, data: Dict = None):
        """Broadcast update to global WebSocket connections"""
        update = {
            "type": "system",
            "update_type": update_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "data": data or {}
        }
        
        for connection in self.global_connections:
            try:
                await connection.send_text(json.dumps(update))
            except:
                pass

manager = ConnectionManager()

# Job manager for real browser automation
class LiveJobManager:
    def __init__(self):
        self.jobs = {}
        self.pending_approvals = {}  # job_id -> approval_event
        self.approval_data = {}  # job_id -> form_data
        self.job_screenshots = {}  # job_id -> latest screenshot
    
    def create_job(self, request: FormFillingRequest) -> str:
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {
            "job_id": job_id,
            "status": JobStatus.QUEUED,
            "request_data": request.dict(),
            "created_at": datetime.now(),
            "progress_percentage": 0,
            "current_step": "Job created",
            "result": None,
            "error": None
        }
        print(f"📋 Created job {job_id} - Status: {JobStatus.QUEUED}")
        print(f"   Target URL: {request.target_url}")
        print(f"   Requires approval: {request.require_human_approval}")
        return job_id
    
    async def process_job_with_real_browser(self, job_id: str):
        """Process job using real browser automation"""
        job = self.jobs.get(job_id)
        if not job:
            print(f"❌ Job {job_id} not found")
            return
        
        try:
            print(f"🚀 Processing job {job_id}")
            job["status"] = JobStatus.RUNNING
            await manager.broadcast_job_update(job_id, "status_change", "Job started", {"status": "running"})
            
            # Create browser agent based on engine selection
            request_data = job["request_data"]
            browser_engine = request_data.get("browser_engine", "default")
            
            # Choose agent based on browser engine
            if browser_engine == "puppeteer":
                from ..agents.puppeteer_browser_agent import PuppeteerBrowserAgent
                agent = PuppeteerBrowserAgent(
                    headless=request_data.get("headless", False),
                    cdp_url=request_data.get("cdp_url", "http://localhost:9222"),
                    api_key=os.getenv("GOOGLE_API_KEY"),
                    manage_server=request_data.get("manage_puppeteer_server", True),
                    server_path=request_data.get("puppeteer_server_path", None)
                )
            else:
                # Default to SimpleBrowserAgent for browser-use
                agent = SimpleBrowserAgent(
                    headless=request_data.get("headless", False),
                    api_key=os.getenv("GOOGLE_API_KEY")
                )
            
            # Set up callbacks for progress and approval
            async def progress_callback(progress_data):
                job["progress_percentage"] = progress_data["progress_percentage"]
                job["current_step"] = progress_data["message"]
                await manager.broadcast_job_update(
                    job_id, "progress", progress_data["message"], 
                    {"progress": progress_data["progress_percentage"]}
                )
            
            async def approval_callback(form_data):
                print(f"⏳ Job {job_id} requesting approval")
                print(f"   Form data: {form_data}")
                
                # Store form data for approval
                self.approval_data[job_id] = form_data
                
                # Update job status
                job["status"] = JobStatus.WAITING_FOR_APPROVAL
                print(f"   Status updated to: {JobStatus.WAITING_FOR_APPROVAL}")
                
                # Create approval event
                approval_event = asyncio.Event()
                self.pending_approvals[job_id] = approval_event
                print(f"   Added to pending approvals. Total pending: {len(self.pending_approvals)}")
                
                # Broadcast approval required
                await manager.broadcast_job_update(
                    job_id, "approval_required", 
                    "Human approval required before form submission",
                    {"form_preview": form_data}
                )
                print(f"   Broadcasted approval_required event")
                
                # Wait for approval decision
                print(f"   Waiting for human approval...")
                await approval_event.wait()
                
                # Check if approved
                approved = job.get("approved", False)
                print(f"   Approval decision: {approved}")
                return approved
            
            async def screenshot_callback(screenshot_data):
                """Handle screenshot updates from browser agent"""
                print(f"📸 Job {job_id} screenshot received")
                
                # Store latest screenshot
                self.job_screenshots[job_id] = screenshot_data
                
                # Broadcast screenshot update
                await manager.broadcast_job_update(
                    job_id, "screenshot_update", 
                    "Browser screenshot updated",
                    {"screenshot_available": True, "timestamp": screenshot_data.get("timestamp")}
                )
            
            agent.set_progress_callback(progress_callback)
            agent.set_approval_callback(approval_callback)
            agent.set_screenshot_callback(screenshot_callback)
            
            # Configure continuous monitoring for live updates
            agent.set_screenshot_interval(1.5)  # Screenshot every 1.5 seconds
            
            # Execute the job
            if request_data.get("target_url", "").startswith("http"):
                if browser_engine == "puppeteer":
                    result = await agent.fill_generic_form_puppeteer(
                        target_url=request_data["target_url"],
                        platform=request_data["platform"],
                        form_type=request_data.get("form_type", "contact"),
                        priority=request_data.get("priority", "normal"),
                        subject=request_data.get("subject", ""),
                        description=request_data["description"],
                        contact_info=request_data.get("contact_info", {}),
                        reference_urls=request_data.get("reference_urls", []),
                        additional_comments=request_data.get("additional_comments", ""),
                        uploaded_files=request_data.get("uploaded_files", []),
                        requires_approval=request_data.get("require_human_approval", True)
                    )
                else:
                    # Default browser-use agent
                    result = await agent.fill_generic_form_simple(
                        target_url=request_data["target_url"],
                        platform=request_data["platform"],
                        form_type=request_data.get("form_type", "contact"),
                        priority=request_data.get("priority", "normal"),
                        subject=request_data.get("subject", ""),
                        description=request_data["description"],
                        contact_info=request_data["contact_info"],
                        reference_urls=request_data.get("reference_urls", []),
                        additional_comments=request_data.get("additional_comments", ""),
                        uploaded_files=request_data.get("uploaded_files", []),
                        requires_approval=request_data.get("require_human_approval", True)
                    )
            else:
                result = {"success": False, "error": "Invalid target URL"}
            
            # Update job with result
            job["result"] = result
            
            if result.get("success"):
                job["status"] = JobStatus.COMPLETED
                job["progress_percentage"] = 100
                await manager.broadcast_job_update(
                    job_id, "completion", "Job completed successfully", 
                    {"result": result}
                )
            else:
                job["status"] = JobStatus.FAILED
                job["error"] = result.get("error", "Unknown error")
                await manager.broadcast_job_update(
                    job_id, "error", f"Job failed: {job['error']}", 
                    {"error": job["error"]}
                )
            
        except Exception as e:
            job["status"] = JobStatus.FAILED
            job["error"] = str(e)
            print(f"❌ Job {job_id} failed: {e}")  # Console logging
            import traceback
            traceback.print_exc()  # Full stack trace
            await manager.broadcast_job_update(
                job_id, "error", f"Job failed with exception: {str(e)}", 
                {"error": str(e)}
            )
        
        finally:
            # Clean up approval data and screenshots
            self.pending_approvals.pop(job_id, None)
            self.approval_data.pop(job_id, None)
            # Keep screenshots for a while for completed job review
            # self.job_screenshots.pop(job_id, None)
    
    async def approve_job(self, job_id: str, approved: bool, reason: str = None, analyst_name: str = None):
        """Approve or reject a pending job"""
        job = self.jobs.get(job_id)
        if not job:
            return False
        
        if job_id not in self.pending_approvals:
            return False
        
        # Set approval decision
        job["approved"] = approved
        job["approval_reason"] = reason
        job["approved_by"] = analyst_name
        
        if approved:
            job["status"] = JobStatus.APPROVED
            await manager.broadcast_job_update(
                job_id, "approval_received", 
                f"Job approved by {analyst_name}: {reason}",
                {"approved": True, "analyst": analyst_name}
            )
        else:
            job["status"] = JobStatus.REJECTED
            await manager.broadcast_job_update(
                job_id, "approval_received", 
                f"Job rejected by {analyst_name}: {reason}",
                {"approved": False, "analyst": analyst_name}
            )
        
        # Signal the approval event
        approval_event = self.pending_approvals.get(job_id)
        if approval_event:
            approval_event.set()
        
        return True
    
    def get_pending_approvals(self) -> List[str]:
        """Get list of jobs waiting for approval"""
        pending_list = list(self.pending_approvals.keys())
        print(f"🔍 get_pending_approvals called - Found {len(pending_list)} pending: {pending_list}")
        return pending_list

# Global job manager
job_manager = LiveJobManager()

# FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Live Browser Automation Server...")
    print("🔧 Browser-use agent ready for real browser automation")
    print("👁️  Set headless=False to watch browser activity live!")
    yield
    print("🛑 Shutting down server...")

app = FastAPI(
    title="Live Browser Automation with Human Approval",
    description="Real browser automation using browser-use with human approval workflow",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# File storage configuration
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Mount static files for uploaded content
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Routes
@app.post("/api/v1/form/submit")
async def submit_form_filling_job(request: FormFillingRequest):
    print(f"🚀 API: Received form filling request")
    print(f"   URL: {request.target_url}")
    print(f"   Platform: {request.platform}")
    print(f"   Form Type: {request.form_type}")
    
    job_id = job_manager.create_job(request)
    
    # Start job processing in background
    print(f"📋 API: Starting background job processing for {job_id}")
    asyncio.create_task(job_manager.process_job_with_real_browser(job_id))
    
    return {"job_id": job_id, "status": "Form filling job submitted successfully"}

@app.post("/api/v1/files/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file (TXT, PDF, or Image)"""
    try:
        # Validate file type
        allowed_types = {
            'text/plain': ['.txt'],
            'application/pdf': ['.pdf'],
            'image/jpeg': ['.jpg', '.jpeg'],
            'image/png': ['.png'],
            'image/gif': ['.gif']
        }
        
        file_extension = Path(file.filename).suffix.lower()
        content_type = file.content_type
        
        if content_type not in allowed_types or file_extension not in allowed_types.get(content_type, []):
            raise HTTPException(status_code=400, detail=f"File type not supported. Allowed types: TXT, PDF, JPG, PNG, GIF")
        
        # Check file size (10MB limit)
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB")
        
        # Generate unique filename
        file_id = str(uuid.uuid4())
        filename = f"{file_id}_{file.filename}"
        file_path = UPLOAD_DIR / filename
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        # Process file based on type
        file_info = {
            "file_id": file_id,
            "original_name": file.filename,
            "filename": filename,
            "content_type": content_type,
            "size": len(content),
            "file_url": f"/uploads/{filename}"
        }
        
        # Extract text content for text processing
        if content_type == 'text/plain':
            text_content = content.decode('utf-8')
            file_info["text_content"] = text_content[:1000]  # First 1000 chars for preview
        elif content_type == 'application/pdf':
            try:
                # Extract text from PDF
                with open(file_path, 'rb') as pdf_file:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    text_content = ""
                    for page in pdf_reader.pages[:5]:  # First 5 pages
                        text_content += page.extract_text() + "\n"
                    file_info["text_content"] = text_content[:1000]  # First 1000 chars
            except Exception as e:
                print(f"Error extracting PDF text: {e}")
                file_info["text_content"] = "[PDF text extraction failed]"
        elif content_type.startswith('image/'):
            try:
                # Get image dimensions
                image = Image.open(file_path)
                file_info["image_dimensions"] = {"width": image.width, "height": image.height}
                file_info["text_content"] = f"[Image: {image.width}x{image.height}]"
            except Exception as e:
                print(f"Error processing image: {e}")
                file_info["text_content"] = "[Image processing failed]"
        
        print(f"📁 File uploaded: {file.filename} ({len(content)} bytes)")
        return file_info
        
    except Exception as e:
        print(f"❌ File upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/jobs/{job_id}")
async def get_job_status(job_id: str):
    print(f"📋 API: get_job_status called for {job_id}")
    job = job_manager.jobs.get(job_id)
    if not job:
        print(f"   ❌ Job {job_id} not found")
        raise HTTPException(status_code=404, detail="Job not found")
    print(f"   ✅ Job found - Status: {job['status']}, Progress: {job['progress_percentage']}%")
    return job

@app.get("/api/v1/approval/pending")
async def get_pending_approvals():
    print(f"📋 API: get_pending_approvals endpoint called")
    pending = job_manager.get_pending_approvals()
    print(f"   Returning: {pending}")
    return pending

@app.get("/api/v1/approval/{job_id}/preview")
async def get_approval_preview(job_id: str):
    job = job_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    form_data = job_manager.approval_data.get(job_id, {})
    
    return {
        "job_id": job_id,
        "status": job["status"],
        "form_preview": form_data,
        "progress_percentage": job["progress_percentage"],
        "current_step": job.get("current_step", "")
    }

@app.post("/api/v1/approval/{job_id}/approve")
async def approve_job(job_id: str, approval: HumanApprovalRequest):
    success = await job_manager.approve_job(
        job_id, approval.approved, approval.reason, approval.analyst_name
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or not pending approval")
    
    return {
        "success": True,
        "job_id": job_id,
        "approved": approval.approved,
        "analyst_name": approval.analyst_name
    }

@app.get("/api/v1/approval/stats")
async def get_approval_stats():
    all_jobs = list(job_manager.jobs.values())
    pending = len([j for j in all_jobs if j["status"] == JobStatus.WAITING_FOR_APPROVAL])
    approved = len([j for j in all_jobs if j["status"] == JobStatus.APPROVED])
    rejected = len([j for j in all_jobs if j["status"] == JobStatus.REJECTED])
    
    return {
        "pending_approvals": pending,
        "approved_jobs": approved,
        "rejected_jobs": rejected,
        "approval_rate_percentage": (approved / (approved + rejected) * 100) if (approved + rejected) > 0 else 0
    }

@app.get("/api/v1/jobs/{job_id}/screenshot")
async def get_job_screenshot(job_id: str):
    """Get the latest screenshot for a job"""
    if job_id not in job_manager.jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    screenshot_data = job_manager.job_screenshots.get(job_id)
    if not screenshot_data:
        raise HTTPException(status_code=404, detail="No screenshot available for this job")
    
    return {
        "job_id": job_id,
        "screenshot": screenshot_data.get("screenshot"),
        "timestamp": screenshot_data.get("timestamp"),
        "format": screenshot_data.get("format", "png")
    }

@app.post("/api/v1/jobs/{job_id}/screenshot/refresh")
async def force_screenshot_refresh(job_id: str):
    """Force a manual screenshot refresh for a job"""
    if job_id not in job_manager.jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_manager.jobs[job_id]
    
    # Check if job is active
    if job["status"] not in [JobStatus.RUNNING, JobStatus.WAITING_FOR_APPROVAL]:
        raise HTTPException(status_code=400, detail="Job is not active - cannot refresh screenshot")
    
    # This would ideally trigger the agent to take a fresh screenshot
    # For now, we'll return a response indicating refresh was requested
    await manager.broadcast_job_update(
        job_id, "screenshot_refresh_requested", 
        "Manual screenshot refresh requested",
        {"refresh_requested": True, "timestamp": datetime.now().isoformat()}
    )
    
    return {
        "job_id": job_id,
        "refresh_requested": True,
        "message": "Screenshot refresh requested - new screenshot will be available shortly"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "active_jobs": len([j for j in job_manager.jobs.values() if j["status"] == JobStatus.RUNNING]),
        "pending_approvals": len(job_manager.pending_approvals)
    }

@app.get("/api/v1/jobs/{job_id}/monitor", response_class=HTMLResponse)
async def monitor_job_browser(job_id: str):
    """Remote browser monitoring for analysts"""
    job = job_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return HTMLResponse(content=f"""
<!DOCTYPE html>
<html>
<head>
    <title>🔍 Browser Monitor - Job {job_id[:8]}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .monitor-container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .job-info {{ background: #e8f4f8; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .status-indicator {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; }}
        .status-running {{ background: #27ae60; animation: pulse 1s infinite; }}
        .status-waiting {{ background: #f39c12; animation: pulse 1s infinite; }}
        .status-completed {{ background: #3498db; }}
        .live-feed {{ border: 2px solid #ddd; border-radius: 8px; padding: 20px; text-align: center; min-height: 300px; }}
        .refresh-btn {{ background: #667eea; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }}
        @keyframes pulse {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} 100% {{ opacity: 1; }} }}
        .instructions {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 4px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 Remote Browser Monitor</h1>
        <p>Monitoring Job: {job_id[:8]}... - Real-time browser activity view for analysts</p>
    </div>
    
    <div class="job-info">
        <h3>📋 Job Information</h3>
        <p><strong>Job ID:</strong> {job_id}</p>
        <p><strong>Target URL:</strong> {job.get('request_data', {}).get('target_url', 'N/A')}</p>
        <p><strong>Platform:</strong> {job.get('request_data', {}).get('platform', 'N/A')}</p>
        <p><strong>Status:</strong> <span id="jobStatus" class="status-indicator status-running"></span><span id="statusText">{job.get('status', 'unknown')}</span></p>
        <p><strong>Progress:</strong> <span id="progressText">{job.get('progress_percentage', 0)}%</span></p>
        <p><strong>Current Step:</strong> <span id="currentStep">{job.get('current_step', 'Processing...')}</span></p>
    </div>
    
    <div class="instructions">
        <strong>📱 For Live Browser Viewing:</strong>
        <ul>
            <li><strong>Local Setup:</strong> Use VNC or remote desktop to view the server machine's screen</li>
            <li><strong>Screen Sharing:</strong> Set up screen sharing software (TeamViewer, Chrome Remote Desktop, etc.)</li>
            <li><strong>Browser Window:</strong> Ensure job is running with headless=false to see browser activity</li>
            <li><strong>Direct Access:</strong> For cloud deployments, use VNC viewer or remote desktop connection</li>
        </ul>
    </div>
    
    <div class="monitor-container">
        <h3>🎬 Browser Activity Monitor</h3>
        <div style="margin-bottom: 15px;">
            <button class="refresh-btn" onclick="refreshStatus()">🔄 Refresh Status</button>
            <button class="refresh-btn" onclick="forceScreenshotRefresh()" style="margin-left: 10px; background: #e74c3c;">
                📸 Force Screenshot Refresh
            </button>
            <button class="refresh-btn" onclick="toggleFastPolling()" id="fastPollingBtn" style="margin-left: 10px; background: #f39c12;">
                ⚡ Enable Fast Polling
            </button>
        </div>
        
        <div class="live-feed" id="liveFeed">
            <h4>📺 Live Browser View</h4>
            <div id="screenshotContainer" style="border: 2px solid #ddd; border-radius: 8px; padding: 10px; margin-bottom: 20px; background: #f9f9f9; min-height: 400px; text-align: center;">
                <img id="browserScreenshot" style="max-width: 100%; height: auto; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);" 
                     src="" alt="Browser screenshot will appear here" />
                <p id="screenshotStatus">📷 Waiting for browser screenshots...</p>
            </div>
            
            <h4>📋 Activity Log</h4>
            <div id="activityLog" style="max-height: 200px; overflow-y: auto; background: #f8f9fa; padding: 10px; border-radius: 4px;">
                <p><em>Waiting for activity updates...</em></p>
            </div>
        </div>
    </div>
    
    <script>
        let ws = null;
        
        function connectWebSocket() {{
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${{protocol}}//${{window.location.host}}/ws/job/{job_id}`);
            
            ws.onopen = function() {{
                console.log('📡 Connected to job monitoring');
                logActivity('📡 Connected to real-time monitoring');
            }};
            
            ws.onmessage = function(event) {{
                const data = JSON.parse(event.data);
                console.log('📨 Monitor received:', data);
                
                // Update job status
                updateJobStatus(data);
                
                // Handle screenshot updates
                if (data.update_type === 'screenshot_update') {{
                    updateScreenshot();
                    logActivity(`📸 Browser screenshot updated`);
                }} else {{
                    // Log other activity
                    logActivity(`${{data.update_type}}: ${{data.message}}`);
                }}
            }};
            
            ws.onclose = function() {{
                console.log('📡 Monitor connection closed, reconnecting...');
                logActivity('📡 Connection lost, reconnecting...');
                setTimeout(connectWebSocket, 3000);
            }};
        }}
        
        function updateJobStatus(data) {{
            if (data.job_id === '{job_id}') {{
                if (data.data && data.data.status) {{
                    document.getElementById('statusText').textContent = data.data.status;
                    const indicator = document.getElementById('jobStatus');
                    indicator.className = 'status-indicator status-' + (data.data.status === 'running' ? 'running' : 
                                          data.data.status === 'waiting_for_approval' ? 'waiting' : 'completed');
                }}
                if (data.data && data.data.progress !== undefined) {{
                    document.getElementById('progressText').textContent = data.data.progress + '%';
                }}
                if (data.message) {{
                    document.getElementById('currentStep').textContent = data.message;
                }}
            }}
        }}
        
        function logActivity(message) {{
            const log = document.getElementById('activityLog');
            const timestamp = new Date().toLocaleTimeString();
            const entry = document.createElement('p');
            entry.innerHTML = `<strong>[${{timestamp}}]</strong> ${{message}}`;
            log.insertBefore(entry, log.firstChild);
            
            // Keep only last 10 entries
            while (log.children.length > 10) {{
                log.removeChild(log.lastChild);
            }}
        }}
        
        async function updateScreenshot() {{
            try {{
                const response = await fetch('/api/v1/jobs/{job_id}/screenshot');
                if (response.ok) {{
                    const screenshotData = await response.json();
                    const img = document.getElementById('browserScreenshot');
                    const status = document.getElementById('screenshotStatus');
                    
                    if (screenshotData.screenshot) {{
                        img.src = `data:image/png;base64,${{screenshotData.screenshot}}`;
                        img.style.display = 'block';
                        status.textContent = `📸 Screenshot updated: ${{new Date(screenshotData.timestamp).toLocaleTimeString()}}`;
                        status.style.color = '#27ae60';
                    }}
                }} else if (response.status === 404) {{
                    document.getElementById('screenshotStatus').textContent = '📷 No screenshot available yet';
                    document.getElementById('screenshotStatus').style.color = '#95a5a6';
                }}
            }} catch (error) {{
                console.error('Screenshot update error:', error);
                document.getElementById('screenshotStatus').textContent = '❌ Screenshot update failed';
                document.getElementById('screenshotStatus').style.color = '#e74c3c';
            }}
        }}
        
        async function refreshStatus() {{
            try {{
                const response = await fetch('/api/v1/jobs/{job_id}');
                if (response.ok) {{
                    const job = await response.json();
                    document.getElementById('statusText').textContent = job.status;
                    document.getElementById('progressText').textContent = job.progress_percentage + '%';
                    document.getElementById('currentStep').textContent = job.current_step || 'Processing...';
                    logActivity(`Status refreshed: ${{job.status}} (${{job.progress_percentage}}%)`);
                }}
            }} catch (error) {{
                logActivity('❌ Failed to refresh status');
            }}
        }}
        
        let fastPolling = false;
        let statusInterval = null;
        let screenshotInterval = null;
        
        function startPolling() {{
            // Clear existing intervals
            if (statusInterval) clearInterval(statusInterval);
            if (screenshotInterval) clearInterval(screenshotInterval);
            
            const statusDelay = fastPolling ? 2000 : 5000;
            const screenshotDelay = fastPolling ? 1000 : 3000;
            
            statusInterval = setInterval(refreshStatus, statusDelay);
            screenshotInterval = setInterval(updateScreenshot, screenshotDelay);
            
            console.log(`Polling: Status every ${{statusDelay}}ms, Screenshots every ${{screenshotDelay}}ms`);
        }}
        
        function toggleFastPolling() {{
            fastPolling = !fastPolling;
            const btn = document.getElementById('fastPollingBtn');
            
            if (fastPolling) {{
                btn.textContent = '🐌 Disable Fast Polling';
                btn.style.background = '#27ae60';
                logActivity('⚡ Fast polling enabled (1s screenshots, 2s status)');
            }} else {{
                btn.textContent = '⚡ Enable Fast Polling';
                btn.style.background = '#f39c12';
                logActivity('🐌 Normal polling enabled (3s screenshots, 5s status)');
            }}
            
            startPolling();
        }}
        
        async function forceScreenshotRefresh() {{
            try {{
                const response = await fetch('/api/v1/jobs/{job_id}/screenshot/refresh', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}}
                }});
                
                if (response.ok) {{
                    const result = await response.json();
                    logActivity('📸 Manual screenshot refresh requested');
                    
                    // Force immediate screenshot update after short delay
                    setTimeout(updateScreenshot, 1000);
                }} else {{
                    const errorText = await response.text();
                    logActivity(`❌ Screenshot refresh failed: ${{response.status}}`);
                }}
            }} catch (error) {{
                logActivity(`❌ Screenshot refresh error: ${{error}}`);
            }}
        }}
        
        // Initialize
        connectWebSocket();
        startPolling();
        
        // Initial screenshot load
        updateScreenshot();
        
        // Initial activity log
        logActivity('🔍 Browser monitoring started for job {job_id[:8]}...');
        logActivity('💡 Tip: Use "Force Screenshot Refresh" to capture manual changes');
        logActivity('💡 Tip: Enable "Fast Polling" for real-time updates');
    </script>
</body>
</html>
    """)

# WebSocket endpoints
@app.websocket("/ws/job/{job_id}")
async def websocket_job_endpoint(websocket: WebSocket, job_id: str):
    await manager.connect_job(websocket, job_id)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except:
        manager.disconnect_job(websocket, job_id)

@app.websocket("/ws/global")
async def websocket_global_endpoint(websocket: WebSocket):
    await manager.connect_global(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except:
        manager.disconnect_global(websocket)

# Enhanced dashboard with live browser info
@app.get("/dashboard", response_class=HTMLResponse) 
async def dashboard():
    return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <title>🤖 Generic Web Form Filling Agent</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background: #f8f9fa; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: linear-gradient(135deg, #007bff 0%, #28a745 100%); color: white; padding: 25px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .alert { background: #e8f4f8; border: 1px solid #bee5eb; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .stats { display: flex; gap: 15px; margin-bottom: 20px; }
        .stat-card { background: white; padding: 15px; border-radius: 8px; flex: 1; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-value { font-size: 24px; font-weight: bold; color: #3498db; }
        .jobs-container { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .job-item { border-bottom: 1px solid #eee; padding: 15px 0; display: flex; justify-content: space-between; align-items: center; }
        .approval-btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; margin: 0 5px; }
        .approve-btn { background: #27ae60; color: white; }
        .reject-btn { background: #e74c3c; color: white; }
        .submit-form { background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 2px dashed #6c757d; }
        .form-field { margin-bottom: 10px; }
        .form-field input, .form-field textarea, .form-field select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        .file-upload-area { border: 2px dashed #007bff; border-radius: 8px; padding: 20px; text-align: center; margin: 10px 0; background: #f8f9fa; transition: all 0.3s ease; }
        .file-upload-area:hover { border-color: #28a745; background: #e8f5e9; }
        .file-upload-area.dragover { border-color: #28a745; background: #e8f5e9; transform: scale(1.02); }
        .uploaded-files { margin-top: 10px; }
        .file-item { display: flex; align-items: center; justify-content: space-between; padding: 8px; margin: 4px 0; background: #e3f2fd; border-radius: 4px; border-left: 4px solid #2196f3; }
        .file-item .file-info { display: flex; align-items: center; flex: 1; }
        .file-item .file-icon { margin-right: 8px; font-size: 16px; }
        .file-item .file-name { font-weight: 500; margin-right: 8px; }
        .file-item .file-size { color: #666; font-size: 12px; }
        .file-item .remove-file { background: #f44336; color: white; border: none; border-radius: 50%; width: 20px; height: 20px; cursor: pointer; font-size: 12px; }
        .file-drop-text { color: #666; margin: 10px 0; }
        .submit-btn { background: #667eea; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
        .live-indicator { display: inline-block; width: 10px; height: 10px; background: #27ae60; border-radius: 50%; margin-right: 5px; animation: pulse 1s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        .browser-note { background: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 4px; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Generic Web Form Filling Agent</h1>
            <p><span class="live-indicator"></span>AI-powered form filling for any website with intelligent field detection</p>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px;">
            <div style="background: #e3f2fd; padding: 15px; border-radius: 8px; border: 1px solid #2196f3;">
                <h4 style="margin: 0 0 10px 0; color: #1976d2;">🔍 CAPTCHA Solving</h4>
                <ul style="margin: 0; padding-left: 20px; font-size: 0.9em;">
                    <li>Automatic CAPTCHA detection</li>
                    <li>Supports reCAPTCHA v2/v3</li>
                    <li>hCaptcha support</li>
                    <li>Image CAPTCHA solving</li>
                </ul>
            </div>
            <div style="background: #e8f5e9; padding: 15px; border-radius: 8px; border: 1px solid #4caf50;">
                <h4 style="margin: 0 0 10px 0; color: #2e7d32;">📎 File Upload Automation</h4>
                <ul style="margin: 0; padding-left: 20px; font-size: 0.9em;">
                    <li>Auto-detect file input fields</li>
                    <li>Upload multiple files</li>
                    <li>Smart field mapping</li>
                    <li>Drag & drop support</li>
                </ul>
            </div>
        </div>
        
        <div class="browser-note">
            <strong>🎯 Smart Form Filling!</strong> Set headless=false to watch the AI agent automatically navigate to any website, detect form fields, and fill them with your custom data using intelligent field matching.
        </div>
        
        <div class="alert">
            <h4>🔴 Auto-Monitoring Settings</h4>
            <label>
                <input type="checkbox" id="autoMonitorEnabled"> 
                <strong>Auto-open monitor windows for active/pending jobs</strong>
            </label>
            <p><small>When enabled, monitoring windows will automatically open for running and pending jobs. You can manually open monitors using the buttons below.</small></p>
        </div>
        
        <div class="submit-form">
            <h3>📝 Generic Form Filling Request</h3>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div>
                    <h4>🎯 Target Form Information</h4>
                    <div class="form-field">
                        <label>Target Form URL:</label>
                        <input type="text" id="targetUrl" placeholder="https://example.com/contact" value="https://httpbin.org/forms/post">
                    </div>
                    <div class="form-field">
                        <label>Website/Platform Name:</label>
                        <input type="text" id="platform" placeholder="Company Name, Website, etc." value="Example Website">
                    </div>
                    <div class="form-field">
                        <label>Form Type/Purpose:</label>
                        <select id="formType">
                            <option value="contact">Contact Form</option>
                            <option value="support">Support Request</option>
                            <option value="inquiry">General Inquiry</option>
                            <option value="feedback">Feedback/Review</option>
                            <option value="application">Application Form</option>
                            <option value="registration">Registration Form</option>
                            <option value="complaint">Complaint Form</option>
                            <option value="quote">Quote Request</option>
                            <option value="other">Other</option>
                        </select>
                    </div>
                    <div class="form-field">
                        <label>Priority Level:</label>
                        <select id="priority">
                            <option value="normal">Normal</option>
                            <option value="high">High</option>
                            <option value="urgent">Urgent</option>
                            <option value="low">Low</option>
                        </select>
                    </div>
                </div>
                <div>
                    <h4>👤 Your Information</h4>
                    <div class="form-field">
                        <label>Full Name:</label>
                        <input type="text" id="contactName" placeholder="John Doe" value="John Smith">
                    </div>
                    <div class="form-field">
                        <label>Email Address:</label>
                        <input type="email" id="contactEmail" placeholder="john@example.com" value="john@example.com">
                    </div>
                    <div class="form-field">
                        <label>Phone Number:</label>
                        <input type="tel" id="contactPhone" placeholder="+1-555-123-4567" value="">
                    </div>
                    <div class="form-field">
                        <label>Company/Organization:</label>
                        <input type="text" id="company" placeholder="Your Company Name" value="Example Corp">
                    </div>
                    <div class="form-field">
                        <label>Your Role/Title:</label>
                        <input type="text" id="jobTitle" placeholder="Manager, Developer, etc." value="">
                    </div>
                </div>
            </div>
            <div class="form-field">
                <label>Subject/Title:</label>
                <input type="text" id="subject" placeholder="Brief subject line for your message" value="General Inquiry">
            </div>
            <div class="form-field">
                <label>Main Message:</label>
                <textarea id="description" placeholder="Please provide your detailed message, inquiry, or request. This will be used to fill the main message/description field on the target form." rows="4">Hello, I am reaching out regarding your services. Could you please provide more information about your offerings? Thank you for your time.</textarea>
            </div>
            <div class="form-field">
                <label>Reference URLs (comma-separated):</label>
                <input type="text" id="referenceUrls" placeholder="https://reference1.com, https://reference2.com" value="">
            </div>
            <div class="form-field">
                <label>Additional Notes:</label>
                <textarea id="additionalComments" placeholder="Any additional information or special instructions for form filling" rows="2"></textarea>
            </div>
            <div class="form-field">
                <label>📎 File Attachments (TXT, PDF, Images):</label>
                <div style="margin-bottom: 10px; padding: 10px; background: #e8f5e9; border-radius: 8px; border: 1px solid #4caf50;">
                    <strong style="color: #2e7d32;">🚀 Enhanced File Upload Features:</strong>
                    <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.9em; color: #2e7d32;">
                        <li>✅ Direct file upload to our server</li>
                        <li>✅ Automatic file upload to web forms via browser automation</li>
                        <li>✅ Intelligent file input field detection</li>
                        <li>✅ Multi-file upload support</li>
                    </ul>
                </div>
                <div class="file-upload-area" id="fileUploadArea">
                    <div class="file-drop-text">
                        <strong>📁 Drop files here or click to upload</strong><br>
                        <small>Supported: .txt, .pdf, .jpg, .png, .gif (Max 10MB each)</small><br>
                        <small style="color: #4caf50;">Files will be automatically uploaded to form fields when detected</small>
                    </div>
                    <input type="file" id="fileInput" multiple accept=".txt,.pdf,.jpg,.jpeg,.png,.gif" style="display: none;">
                    <button type="button" onclick="document.getElementById('fileInput').click()" style="margin-top: 10px; padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer;">
                        📎 Choose Files
                    </button>
                </div>
                <div class="uploaded-files" id="uploadedFiles"></div>
            </div>
            <div class="form-field">
                <label>🚀 Browser Engine:</label>
                <select id="browserEngine" style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 16px;" onchange="togglePuppeteerOptions()">
                    <option value="browser-use" selected>Browser-Use (AI-Powered)</option>
                    <option value="puppeteer">Puppeteer (CDP)</option>
                </select>
                <small style="color: #666; display: block; margin-top: 5px;">
                    Browser-Use: AI-powered form filling with smart field detection<br>
                    Puppeteer: Direct browser control via Chrome DevTools Protocol
                </small>
                
                <div id="puppeteerOptions" style="display: none; margin-top: 10px; padding: 10px; background: #f0f0f0; border-radius: 4px;">
                    <label style="display: flex; align-items: center;">
                        <input type="checkbox" id="managePuppeteerServer" checked style="margin-right: 8px;">
                        <span>🤖 Automatically manage Puppeteer server</span>
                    </label>
                    <small style="color: #666; display: block; margin-top: 5px; margin-left: 24px;">
                        When checked, the Python agent will automatically start and stop the Node.js Puppeteer server
                    </small>
                </div>
            </div>
            <div class="form-field">
                <label>
                    <input type="checkbox" id="headless"> Run in headless mode (no visible browser)
                </label>
            </div>
            <button class="submit-btn" onclick="submitFormFillingRequest()">🤖 Start Form Filling</button>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value" id="activeJobs">-</div>
                <div>🔄 Active Jobs</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="pendingApprovals">-</div>
                <div>⏳ Pending Approvals</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="completedJobs">-</div>
                <div>✅ Completed</div>
            </div>
        </div>
        
        <div class="jobs-container">
            <h3>🎬 Live Jobs</h3>
            <div id="jobsList">Loading...</div>
        </div>
    </div>
    
    <script>
        // WebSocket for real-time updates
        let ws = null;
        
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws/global`);
            
            ws.onopen = function() {
                console.log('📡 Connected to live updates');
            };
            
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                console.log('📨 Received:', data);
                
                // Immediately refresh jobs on any update
                loadJobs();
                
                // Show live notifications for important events
                if (data.update_type === 'approval_required') {
                    const jobId = data.job_id ? data.job_id.substring(0, 8) : 'Unknown';
                    showNotification(`🔔 Job ${jobId} needs approval!`, 'warning');
                    
                    // Auto-open monitor if enabled and not already open
                    if (document.getElementById('autoMonitorEnabled').checked && data.job_id && !monitorWindows.has(data.job_id)) {
                        setTimeout(() => openMonitorWindow(data.job_id), 1500);
                    }
                } else if (data.update_type === 'completion') {
                    const jobId = data.job_id ? data.job_id.substring(0, 8) : 'Unknown';
                    showNotification(`✅ Job ${jobId} completed!`, 'success');
                } else if (data.update_type === 'status_change' && data.data && data.data.status === 'running') {
                    const jobId = data.job_id ? data.job_id.substring(0, 8) : 'Unknown';
                    showNotification(`🚀 Job ${jobId} started!`, 'info');
                    
                    // Auto-open monitor for newly running job if enabled
                    if (document.getElementById('autoMonitorEnabled').checked && data.job_id && !monitorWindows.has(data.job_id)) {
                        setTimeout(() => openMonitorWindow(data.job_id), 1000);
                    }
                }
            };
            
            ws.onclose = function() {
                console.log('📡 Connection closed, reconnecting...');
                setTimeout(connectWebSocket, 3000);
            };
        }
        
        function showNotification(message, type = 'info') {
            // Create notification element
            const notification = document.createElement('div');
            notification.style.cssText = `
                position: fixed; top: 20px; right: 20px; z-index: 1000;
                padding: 15px 20px; border-radius: 8px; color: white;
                font-weight: bold; box-shadow: 0 4px 8px rgba(0,0,0,0.3);
                background: ${type === 'success' ? '#27ae60' : type === 'warning' ? '#f39c12' : '#3498db'};
                transition: all 0.3s ease;
            `;
            notification.textContent = message;
            
            document.body.appendChild(notification);
            
            // Auto-remove after 5 seconds
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.style.transform = 'translateX(100%)';
                    setTimeout(() => notification.remove(), 300);
                }
            }, 5000);
        }
        
        // Monitor window management
        const monitorWindows = new Map();
        
        function openMonitorWindow(jobId) {
            // Close existing monitor window for this job if it exists
            if (monitorWindows.has(jobId)) {
                const existingWindow = monitorWindows.get(jobId);
                if (existingWindow && !existingWindow.closed) {
                    existingWindow.focus();
                    return;
                }
            }
            
            // Open new monitor window
            const monitorUrl = `/api/v1/jobs/${jobId}/monitor`;
            const windowFeatures = 'width=1200,height=800,scrollbars=yes,resizable=yes,toolbar=no,menubar=no';
            const monitorWindow = window.open(monitorUrl, `monitor_${jobId}`, windowFeatures);
            
            if (monitorWindow) {
                monitorWindows.set(jobId, monitorWindow);
                
                // Clean up when window is closed
                const checkClosed = setInterval(() => {
                    if (monitorWindow.closed) {
                        monitorWindows.delete(jobId);
                        clearInterval(checkClosed);
                    }
                }, 1000);
                
                showNotification(`🔴 Monitoring window opened for job ${jobId.substring(0, 8)}`, 'info');
            } else {
                showNotification('❌ Failed to open monitor window. Check popup blocker.', 'warning');
            }
        }
        
        function autoOpenMonitorForActiveJobs() {
            // Check if auto-monitoring is enabled
            const autoMonitorEnabled = document.getElementById('autoMonitorEnabled').checked;
            if (!autoMonitorEnabled) {
                return;
            }
            
            // Auto-open monitor windows for newly active jobs
            const activeJobs = document.querySelectorAll('[data-job-status="running"], [data-job-status="waiting_for_approval"]');
            
            activeJobs.forEach(jobElement => {
                const jobId = jobElement.getAttribute('data-job-id');
                if (jobId && !monitorWindows.has(jobId)) {
                    // Check if this is a newly active job (not already monitored)
                    console.log(`🔴 Auto-opening monitor for active job: ${jobId.substring(0, 8)}`);
                    setTimeout(() => openMonitorWindow(jobId), 1000); // Small delay to avoid overwhelming
                }
            });
        }
        
        async function submitFormFillingRequest() {
            // Collect all form data for generic form filling
            const data = {
                target_url: document.getElementById('targetUrl').value,
                platform: document.getElementById('platform').value,
                form_type: document.getElementById('formType').value,
                priority: document.getElementById('priority').value,
                subject: document.getElementById('subject').value,
                description: document.getElementById('description').value,
                reference_urls: document.getElementById('referenceUrls').value.split(',').map(url => url.trim()).filter(url => url),
                additional_comments: document.getElementById('additionalComments').value,
                uploaded_files: uploadedFiles.map(file => ({
                    id: file.id,
                    name: file.name,
                    type: file.type,
                    url: file.url
                })),
                contact_info: {
                    name: document.getElementById('contactName').value,
                    email: document.getElementById('contactEmail').value,
                    phone: document.getElementById('contactPhone').value,
                    company: document.getElementById('company').value,
                    job_title: document.getElementById('jobTitle').value
                },
                require_human_approval: true,
                headless: document.getElementById('headless').checked,
                browser_engine: document.getElementById('browserEngine').value,
                manage_puppeteer_server: document.getElementById('browserEngine').value === 'puppeteer' ? 
                    document.getElementById('managePuppeteerServer').checked : false
            };
            
            // Validate required fields
            if (!data.target_url || !data.platform || !data.contact_info.name || !data.contact_info.email) {
                alert('❌ Please fill in all required fields: Target URL, Platform Name, Your Name, and Email');
                return;
            }
            
            try {
                const response = await fetch('/api/v1/form/submit', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                alert('🤖 Form filling request submitted! Job ID: ' + result.job_id + '\\n\\n' + 
                      'The AI agent will automatically navigate to the target form and intelligently fill it with your information.\\n' +
                      (data.headless ? 'Running in headless mode - check the monitor for progress.' : 'Watch the browser window to see the smart form filling in action!'));
                loadJobs();
            } catch (error) {
                alert('❌ Error submitting form filling request: ' + error);
            }
        }
        
        async function approveJob(jobId, approved) {
            try {
                const response = await fetch(`/api/v1/approval/${jobId}/approve`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        approved: approved,
                        reason: approved ? 'Approved via live dashboard' : 'Rejected via live dashboard',
                        analyst_name: 'Live Dashboard User'
                    })
                });
                
                if (response.ok) {
                    alert(approved ? '✅ Job approved! Browser will continue.' : '❌ Job rejected.');
                    loadJobs();
                } else {
                    alert('Error processing approval');
                }
            } catch (error) {
                alert('Error: ' + error);
            }
        }
        
        async function loadJobs() {
            try {
                console.log('🔄 Loading jobs...');
                // Get pending approvals
                const pendingResponse = await fetch('/api/v1/approval/pending');
                const pending = await pendingResponse.json();
                console.log('📋 Pending approvals:', pending);
                document.getElementById('pendingApprovals').textContent = pending.length;
                
                // Show all jobs (for demo, showing pending ones)
                let html = '';
                let completedCount = 0;
                let activeCount = 0;
                
                console.log('📋 Processing', pending.length, 'pending jobs');
                
                for (const jobId of pending) {
                    console.log('🔍 Fetching job details for:', jobId);
                    const jobResponse = await fetch(`/api/v1/jobs/${jobId}`);
                    console.log('📊 Job response status:', jobResponse.status);
                    
                    if (!jobResponse.ok) {
                        console.error('❌ Failed to fetch job:', jobId, jobResponse.status);
                        continue;
                    }
                    
                    const job = await jobResponse.json();
                    console.log('📋 Job data:', job);
                    
                    if (job.status === 'running') activeCount++;
                    if (job.status === 'completed') completedCount++;
                    
                    const statusEmoji = {
                        'queued': '⏳',
                        'running': '🔄',
                        'waiting_for_approval': '⏸️',
                        'approved': '✅',
                        'rejected': '❌',
                        'completed': '🎉',
                        'failed': '💥'
                    };
                    
                    html += `
                        <div class="job-item" data-job-id="${jobId}" data-job-status="${job.status}">
                            <div>
                                <strong>${statusEmoji[job.status] || '📋'} ${jobId.substring(0, 8)}...</strong><br>
                                <small>Status: ${job.status} (${job.progress_percentage}%)</small><br>
                                <small>📝 ${job.current_step || 'Processing...'}</small><br>
                                <small>🌐 ${job.request_data.target_url}</small>
                            </div>
                            <div>
                                ${(job.status === 'running' || job.status === 'waiting_for_approval') ? `
                                    <button class="approval-btn" style="background: #e74c3c; color: white; margin-right: 5px;" 
                                            onclick="openMonitorWindow('${jobId}')">
                                        🔴 LIVE Monitor
                                    </button>
                                ` : `
                                    <button class="approval-btn" style="background: #3498db; color: white; margin-right: 5px;" 
                                            onclick="window.open('/api/v1/jobs/${jobId}/monitor', '_blank')">
                                        🔍 View Monitor
                                    </button>
                                `}
                                ${job.status === 'waiting_for_approval' ? `
                                    <button class="approval-btn approve-btn" onclick="approveJob('${jobId}', true)">✅ Approve</button>
                                    <button class="approval-btn reject-btn" onclick="approveJob('${jobId}', false)">❌ Reject</button>
                                ` : ''}
                            </div>
                        </div>
                    `;
                }
                
                document.getElementById('jobsList').innerHTML = html || '<p>No active jobs</p>';
                document.getElementById('activeJobs').textContent = activeCount;
                document.getElementById('completedJobs').textContent = completedCount;
                
                // Auto-trigger monitoring for active jobs
                setTimeout(autoOpenMonitorForActiveJobs, 500);
                
            } catch (error) {
                console.error('Error loading jobs:', error);
            }
        }
        
        // File upload handling
        let uploadedFiles = [];
        
        function togglePuppeteerOptions() {
            const engine = document.getElementById('browserEngine').value;
            const options = document.getElementById('puppeteerOptions');
            options.style.display = engine === 'puppeteer' ? 'block' : 'none';
        }
        
        function setupFileUpload() {
            const fileInput = document.getElementById('fileInput');
            const fileUploadArea = document.getElementById('fileUploadArea');
            const uploadedFilesDiv = document.getElementById('uploadedFiles');
            
            // File input change handler
            fileInput.addEventListener('change', handleFileSelect);
            
            // Drag and drop handlers
            fileUploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                fileUploadArea.classList.add('dragover');
            });
            
            fileUploadArea.addEventListener('dragleave', (e) => {
                e.preventDefault();
                fileUploadArea.classList.remove('dragover');
            });
            
            fileUploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                fileUploadArea.classList.remove('dragover');
                handleFileSelect({ target: { files: e.dataTransfer.files } });
            });
        }
        
        async function handleFileSelect(event) {
            const files = Array.from(event.target.files);
            
            for (const file of files) {
                if (file.size > 10 * 1024 * 1024) { // 10MB limit
                    alert(`File "${file.name}" is too large. Maximum size is 10MB.`);
                    continue;
                }
                
                if (!isValidFileType(file)) {
                    alert(`File "${file.name}" is not supported. Please use TXT, PDF, JPG, PNG, or GIF files.`);
                    continue;
                }
                
                await uploadFile(file);
            }
            
            // Clear file input
            document.getElementById('fileInput').value = '';
        }
        
        function isValidFileType(file) {
            const validTypes = ['text/plain', 'application/pdf', 'image/jpeg', 'image/jpg', 'image/png', 'image/gif'];
            return validTypes.includes(file.type) || 
                   ['.txt', '.pdf', '.jpg', '.jpeg', '.png', '.gif'].some(ext => file.name.toLowerCase().endsWith(ext));
        }
        
        async function uploadFile(file) {
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                showNotification(`📤 Uploading ${file.name}...`, 'info');
                
                const response = await fetch('/api/v1/files/upload', {
                    method: 'POST',
                    body: formData
                });
                
                if (response.ok) {
                    const result = await response.json();
                    uploadedFiles.push({
                        id: result.file_id,
                        name: file.name,
                        size: file.size,
                        type: file.type,
                        url: result.file_url
                    });
                    
                    updateFilesList();
                    showNotification(`✅ ${file.name} uploaded successfully!`, 'success');
                } else {
                    throw new Error(`Upload failed: ${response.statusText}`);
                }
            } catch (error) {
                console.error('File upload error:', error);
                showNotification(`❌ Failed to upload ${file.name}: ${error.message}`, 'error');
            }
        }
        
        function updateFilesList() {
            const uploadedFilesDiv = document.getElementById('uploadedFiles');
            
            if (uploadedFiles.length === 0) {
                uploadedFilesDiv.innerHTML = '';
                return;
            }
            
            uploadedFilesDiv.innerHTML = uploadedFiles.map(file => `
                <div class="file-item" data-file-id="${file.id}">
                    <div class="file-info">
                        <span class="file-icon">${getFileIcon(file.type)}</span>
                        <span class="file-name">${file.name}</span>
                        <span class="file-size">(${formatFileSize(file.size)})</span>
                    </div>
                    <button class="remove-file" onclick="removeFile('${file.id}')" title="Remove file">×</button>
                </div>
            `).join('');
        }
        
        function getFileIcon(fileType) {
            if (fileType.startsWith('image/')) return '🖼️';
            if (fileType === 'application/pdf') return '📄';
            if (fileType === 'text/plain') return '📝';
            return '📎';
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        function removeFile(fileId) {
            uploadedFiles = uploadedFiles.filter(file => file.id !== fileId);
            updateFilesList();
            showNotification('🗑️ File removed', 'info');
        }
        
        function showNotification(message, type) {
            // Simple notification system
            const notification = document.createElement('div');
            notification.style.cssText = `
                position: fixed; top: 20px; right: 20px; z-index: 1000;
                padding: 12px 20px; border-radius: 4px; color: white; font-weight: bold;
                background: ${type === 'error' ? '#f44336' : type === 'success' ? '#4caf50' : '#2196f3'};
                box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            `;
            notification.textContent = message;
            document.body.appendChild(notification);
            
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.parentElement.removeChild(notification);
                }
            }, 4000);
        }

        // Initialize
        setupFileUpload();
        connectWebSocket();
        loadJobs();
        setInterval(loadJobs, 1000); // More frequent refresh for real-time feel
        
        // Also refresh when window gains focus
        window.addEventListener('focus', loadJobs);
    </script>
</body>
</html>
    """)

if __name__ == "__main__":
    uvicorn.run(
        "live_browser_server:app",
        host="127.0.0.1",
        port=8002,
        reload=False,
        log_level="info"
    )