#!/usr/bin/env python
"""Run Water AI API server.

Usage:
    python -m scripts.run_api_server
    
    Or with environment variables:
    DEEPSEEK_API_KEY=sk-... python -m scripts.run_api_server --host 0.0.0.0 --port 8000
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import uvicorn
from water_ai.api import create_app


def main():
    """Run the API server."""
    parser = argparse.ArgumentParser(
        description="Run Water AI API Server"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)",
    )
    
    args = parser.parse_args()
    
    # Check DeepSeek API key
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        print(f"✓ DEEPSEEK_API_KEY configured (using API backend)")
    else:
        print("⚠ DEEPSEEK_API_KEY not set (using mock/fallback mode)")
    
    # Create app
    app = create_app()
    
    # Run server
    print(f"\n🚀 Starting Water AI API Server")
    print(f"   Host: {args.host}")
    print(f"   Port: {args.port}")
    print(f"   Reload: {args.reload}")
    print(f"\n📖 API Documentation: http://{args.host}:{args.port}/docs")
    print(f"📊 ReDoc: http://{args.host}:{args.port}/redoc")
    print()
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        log_level="info",
    )


if __name__ == "__main__":
    main()
