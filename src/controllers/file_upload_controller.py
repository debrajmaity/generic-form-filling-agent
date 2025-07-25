#!/usr/bin/env python3
"""
File Upload Controller for Browser-Use Integration

This controller handles file uploads in web forms using browser-use automation.
It can detect file input fields and upload files automatically.
"""

import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from browser_use import Controller, action
from browser_use.browser.browser import Browser
from browser_use.context import BrowserContext


class FileUploadController(Controller):
    """Controller for handling file uploads in web forms"""
    
    def __init__(self):
        super().__init__()
        self.uploaded_files: List[Dict[str, Any]] = []
        
    @action("Detect all file input fields on the current page")
    async def detect_file_inputs(self, context: BrowserContext) -> List[Dict[str, Any]]:
        """Detect file input fields on the current page"""
        try:
            page = context.page
            if not page:
                return []
                
            # JavaScript to find all file input elements
            js_code = """
            Array.from(document.querySelectorAll('input[type="file"]')).map(input => ({
                id: input.id,
                name: input.name,
                accept: input.accept,
                multiple: input.multiple,
                required: input.required,
                className: input.className,
                placeholder: input.placeholder,
                label: (function() {
                    // Try to find associated label
                    let label = input.closest('label');
                    if (!label && input.id) {
                        label = document.querySelector('label[for="' + input.id + '"]');
                    }
                    if (!label) {
                        // Look for nearby text
                        let parent = input.parentElement;
                        while (parent && parent.tagName !== 'FORM') {
                            let text = parent.textContent;
                            if (text && text.trim().length > 0 && text.trim().length < 100) {
                                return text.trim();
                            }
                            parent = parent.parentElement;
                        }
                    }
                    return label ? label.textContent.trim() : '';
                })(),
                boundingBox: (function() {
                    let rect = input.getBoundingClientRect();
                    return {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    };
                })()
            }))
            """
            
            file_inputs = await page.evaluate(js_code)
            
            print(f"🔍 Found {len(file_inputs)} file input field(s)")
            for i, input_field in enumerate(file_inputs):
                print(f"   [{i+1}] ID: {input_field.get('id', 'N/A')}, Name: {input_field.get('name', 'N/A')}")
                print(f"       Label: {input_field.get('label', 'N/A')}")
                print(f"       Accept: {input_field.get('accept', 'any')}")
                print(f"       Multiple: {input_field.get('multiple', False)}")
            
            return file_inputs
            
        except Exception as e:
            print(f"❌ Error detecting file inputs: {e}")
            return []
    
    @action("Upload a file to a specific file input field")
    async def upload_file(self, context: BrowserContext, file_path: str, input_selector: str = None) -> bool:
        """Upload a file to a specific file input field"""
        try:
            page = context.page
            if not page:
                self.logger.error("No browser page available")
                return False
                
            if not os.path.exists(file_path):
                self.logger.error(f"File not found: {file_path}")
                return False
                
            # Get file inputs if selector not provided
            if not input_selector:
                file_inputs = await self.detect_file_inputs(context)
                if not file_inputs:
                    self.logger.error("No file input fields found")
                    return False
                    
                # Use first available input
                input_data = file_inputs[0]
                if input_data.get('id'):
                    input_selector = f"#{input_data['id']}"
                elif input_data.get('name'):
                    input_selector = f"input[name='{input_data['name']}']"
                else:
                    input_selector = "input[type='file']"
            
            self.logger.info(f"Uploading file: {Path(file_path).name} to {input_selector}")
            
            # Upload the file using Playwright
            file_input = page.locator(input_selector).first
            await file_input.set_input_files(file_path)
            
            # Verify upload
            await page.wait_for_timeout(1000)  # Wait for upload to process
            
            file_name = await file_input.evaluate("input => input.files[0]?.name")
            if file_name:
                self.logger.info(f"File uploaded successfully: {file_name}")
                self.uploaded_files.append({
                    'path': file_path,
                    'name': Path(file_path).name,
                    'selector': input_selector,
                    'uploaded_name': file_name
                })
                return True
            else:
                self.logger.error("File upload verification failed")
                return False
                
        except Exception as e:
            self.logger.error(f"Error uploading file: {e}")
            return False
    
    @action("Upload multiple files to detected file input fields")
    async def upload_multiple_files(self, context: BrowserContext, file_paths: List[str]) -> Dict[str, Any]:
        """Upload multiple files to detected file input fields"""
        result = {
            'success': True,
            'uploaded_files': [],
            'failed_files': [],
            'inputs_used': []
        }
        
        try:
            file_inputs = await self.detect_file_inputs(context)
            if not file_inputs:
                self.logger.error("No file input fields found")
                result['success'] = False
                return result
            
            # Check for multi-file input
            multi_input = next((inp for inp in file_inputs if inp.get('multiple')), None)
            
            if multi_input:
                # Upload all files to the multiple file input
                selector = f"#{multi_input['id']}" if multi_input.get('id') else f"input[name='{multi_input['name']}']"
                try:
                    file_input = context.page.locator(selector).first
                    await file_input.set_input_files(file_paths)
                    
                    # Verify uploads
                    uploaded_count = await file_input.evaluate("input => input.files.length")
                    self.logger.info(f"Uploaded {uploaded_count} files to multi-file input")
                    
                    result['uploaded_files'] = file_paths
                    result['inputs_used'] = [selector]
                    return result
                    
                except Exception as e:
                    self.logger.error(f"Multi-file upload failed: {e}")
            
            # Fall back to uploading to individual inputs
            for i, file_path in enumerate(file_paths):
                if i < len(file_inputs):
                    input_data = file_inputs[i]
                    selector = None
                    if input_data.get('id'):
                        selector = f"#{input_data['id']}"
                    elif input_data.get('name'):
                        selector = f"input[name='{input_data['name']}']"
                    
                    success = await self.upload_file(context, file_path, selector)
                    if success:
                        result['uploaded_files'].append(file_path)
                        result['inputs_used'].append(selector or f"input[{i}]")
                    else:
                        result['failed_files'].append(file_path)
                else:
                    self.logger.warning(f"No more file inputs for {Path(file_path).name}")
                    result['failed_files'].append(file_path)
            
            if result['failed_files']:
                result['success'] = len(result['uploaded_files']) > 0
            
            self.logger.info(f"Upload summary: {len(result['uploaded_files'])} succeeded, {len(result['failed_files'])} failed")
            return result
            
        except Exception as e:
            self.logger.error(f"Error in multiple file upload: {e}")
            result['success'] = False
            return result
    
    @action("Analyze file upload requirements on the current page")
    async def analyze_file_requirements(self, context: BrowserContext) -> Dict[str, Any]:
        """Analyze the page to understand file upload requirements"""
        try:
            file_inputs = await self.detect_file_inputs(context)
            
            analysis = {
                'total_inputs': len(file_inputs),
                'accepts_multiple': any(inp.get('multiple') for inp in file_inputs),
                'required_files': len([inp for inp in file_inputs if inp.get('required')]),
                'accepted_types': [],
                'max_files': 0,
                'recommendations': []
            }
            
            # Analyze accepted file types
            for inp in file_inputs:
                accept = inp.get('accept', '')
                if accept:
                    types = [t.strip() for t in accept.split(',')]
                    analysis['accepted_types'].extend(types)
            
            analysis['accepted_types'] = list(set(analysis['accepted_types']))
            
            # Calculate max files
            analysis['max_files'] = len(file_inputs)
            if any(inp.get('multiple') for inp in file_inputs):
                analysis['max_files'] = 99  # Assume reasonable limit for multiple
            
            # Generate recommendations
            if analysis['total_inputs'] == 0:
                analysis['recommendations'].append("No file upload fields detected")
            elif analysis['accepts_multiple']:
                analysis['recommendations'].append("Page supports multiple file uploads")
            else:
                analysis['recommendations'].append(f"Upload up to {analysis['total_inputs']} files to separate inputs")
            
            if analysis['accepted_types']:
                types_str = ', '.join(analysis['accepted_types'])
                analysis['recommendations'].append(f"Accepted file types: {types_str}")
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing file requirements: {e}")
            return {'error': str(e)}


# Create controller instance
controller = FileUploadController()