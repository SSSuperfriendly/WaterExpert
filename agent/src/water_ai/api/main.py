"""FastAPI application for Water AI system."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .routes import health, strategy, scenarios, explain

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI instance
    """
    
    # Lifespan context manager
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Startup and shutdown logic."""
        # Startup
        print("🚀 Water AI API Server Starting...")
        print(f"   DeepSeek Backend: {'API' if os.getenv('DEEPSEEK_API_KEY') else 'Mock'}")
        yield
        # Shutdown
        print("🛑 Water AI API Server Shutting Down...")
    
    # Create app
    app = FastAPI(
        title="Water AI Multi-Agent API",
        description="API for water quality management using multi-agent intelligence",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Customize in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(health.router)
    app.include_router(strategy.router)
    app.include_router(scenarios.router)
    app.include_router(explain.router)
    
    # Root endpoint - serve dashboard
    @app.get("/")
    async def root():
        """Serve the dashboard UI."""
        return FileResponse(STATIC_DIR / "index.html")

    # API info endpoint
    @app.get("/api")
    async def api_info():
        """Root API endpoint with information."""
        return {
            "name": "Water AI Multi-Agent System",
            "version": "1.0.0",
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat(),
            "documentation": "/docs",
            "dashboard": "/",
            "health": "/api/health",
            "scenarios": "/api/scenarios",
        }

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    
    # Error handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        """Custom HTTP exception handler."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "status_code": exc.status_code,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        """General exception handler."""
        return JSONResponse(
            status_code=500,
            content={
                "error": str(exc),
                "status_code": 500,
                "message": "Internal server error",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    
    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
