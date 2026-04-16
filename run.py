import uvicorn
import os

if __name__ == "__main__":
    # Get port from environment or use default 8000
    port = int(os.environ.get("PORT", 8000))
    
    print(f"Starting server on http://localhost:{port}")
    print(f"Documentation at http://localhost:{port}/docs")
    
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=port, 
        reload=True
    )
