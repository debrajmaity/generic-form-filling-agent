#!/usr/bin/env python3
"""
Live Browser Agent Setup Script
"""

import os
import subprocess
import sys

def install_requirements():
    """Install Python requirements using uv"""
    print("📦 Installing Python requirements with uv...")
    try:
        subprocess.check_call(["uv", "sync"])
        print("✅ Requirements installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install requirements: {e}")
        print("   Make sure uv is installed: pip install uv")
        return False

def create_env_file():
    """Create .env file if it doesn't exist"""
    if not os.path.exists(".env"):
        print("🔧 Creating .env file...")
        with open(".env", "w") as f:
            f.write("GOOGLE_API_KEY=your-google-api-key-here\n")
        print("✅ Created .env file")
        print("   Please edit .env and add your Google API key")
        print("   Get your key from: https://aistudio.google.com/app/apikey")
    else:
        print("✅ .env file already exists")

def verify_structure():
    """Verify project structure"""
    required_dirs = [
        "src/server",
        "src/agents", 
        "tests",
        "docs",
        "scripts",
        "config"
    ]
    
    required_files = [
        "src/server/live_browser_server.py",
        "src/agents/simple_browser_agent.py",
        "src/agents/real_browser_agent.py",
        "run.py",
        "pyproject.toml"
    ]
    
    print("🔍 Verifying project structure...")
    
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"   ✅ {dir_path}")
        else:
            print(f"   ❌ {dir_path} (missing)")
            return False
    
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"   ✅ {file_path}")
        else:
            print(f"   ❌ {file_path} (missing)")
            return False
    
    return True

def main():
    """Main setup function"""
    print("🚀 Live Browser Agent Setup")
    print("=" * 30)
    
    # Verify project structure
    if not verify_structure():
        print("\n❌ Project structure verification failed")
        print("   Please ensure all required files are present")
        return False
    
    # Create .env file
    create_env_file()
    
    # Install requirements
    if not install_requirements():
        return False
    
    print("\n🎉 Setup completed successfully!")
    print("\n📝 Next steps:")
    print("   1. Edit .env file and add your Google API key")
    print("   2. Start server: uv run python run.py")
    print("   3. Open dashboard: http://localhost:8002/dashboard")
    print("\n🧪 Run tests:")
    print("   uv run python tests/test_screenshot_logic.py")
    print("   uv run python tests/test_continuous_monitoring.py")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)