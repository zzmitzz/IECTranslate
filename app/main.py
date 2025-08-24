import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.rtc.web_socket import websocket_router
from app.config import API_KEY

# Create FastAPI app instance
app = FastAPI(
    title="IEC Translate WebSocket Server",
    description="WebSocket server for real-time communication and WebRTC streaming",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware for WebSocket connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(websocket_router, prefix="/api/v1", tags=["websocket"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "IEC Translate WebSocket Server",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/api-key-info")
async def api_key_info():
    """Get API key information (for development/testing)"""
    return {
        "api_key_header": "x-api-key",
        "api_key_exists": bool(API_KEY),
        "api_key_length": len(API_KEY) if API_KEY else 0
    }

if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # Bind to all available network interfaces
        port=8000,        # Default port
        reload=True,      # Enable auto-reload for development
        log_level="info",
        access_log=True
    )