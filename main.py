from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json
import httpx
import websockets # Used implicitly by FastAPI for WebSockets
from datetime import datetime
import asyncio
import logging

# --- Configuration & Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mobile Emulator Backend")

# --- CORS ---
# Allow all origins for simple demo purposes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-Memory User Store ---
# NOTE: NEVER use this in production. Use a proper database.
users_db: Dict[str, str] = {} # {username: password}

# --- Pydantic Models ---
class UserCredentials(BaseModel):
    username: str
    password: str

class UserUpdate(BaseModel):
    password: str # Only allow password update for simplicity

class LLMPrompt(BaseModel):
    username: str
    prompt: str

# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected: {websocket.client}")

    async def broadcast(self, message: str):
        # Use asyncio.gather for concurrent sending
        results = await asyncio.gather(
            *[connection.send_text(message) for connection in self.active_connections],
            return_exceptions=True # Don't let one failed send stop others
        )
        # Log any errors during broadcast
        for result, connection in zip(results, self.active_connections):
            if isinstance(result, Exception):
                logger.error(f"Failed to send message to {connection.client}: {result}")
                # Optionally disconnect clients that cause errors
                # self.disconnect(connection)


manager = ConnectionManager()

# --- Logging Utility ---
async def log_and_broadcast(log_data: Dict[str, Any]):
    """Adds timestamp and broadcasts log data via WebSocket."""
    try:
        log_data["timestamp"] = datetime.now().isoformat()
        log_str = json.dumps(log_data) # No indentation for transmission efficiency
        await manager.broadcast(log_str)
        # Also log to server console
        logger.info(f"Broadcasting Log: {log_str}")
    except Exception as e:
        logger.error(f"Error broadcasting log: {e}")

# --- Helper to format log data ---
def format_log(source: str, method: Optional[str] = None, url: Optional[str] = None,
               status: Optional[int] = None, request_payload: Optional[Any] = None,
               response_payload: Optional[Any] = None, detail: Optional[str] = None):
    log_entry = {"source": source}
    if method: log_entry["method"] = method
    if url: log_entry["url"] = url
    if status: log_entry["status"] = status
    if request_payload: log_entry["request_payload"] = request_payload
    if response_payload: log_entry["response_payload"] = response_payload
    if detail: log_entry["detail"] = detail
    return log_entry

# --- WebSocket Endpoint ---
@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Keep the connection alive, listening for potential messages (though we don't process them here)
        while True:
            # We don't expect messages FROM the client in this setup,
            # but receive_text keeps the connection open and handles pings.
            # If the client disconnects, it will raise WebSocketDisconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error on {websocket.client}: {e}")
        manager.disconnect(websocket)


# --- Serve Frontend Files ---
@app.get("/", response_class=HTMLResponse)
async def serve_phonemulator_html():
    try:
        with open("phonemulator.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="phonemulator.html not found")

@app.get("/style.css")
async def serve_style_css():
    try:
        with open("style.css", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/css")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="style.css not found")

@app.get("/script.js")
async def serve_script_js():
    try:
        with open("script.js", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="application/javascript")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="script.js not found")


# --- API Endpoints ---

@app.post("/register/")
async def register_user(user: UserCredentials, request: Request):
    url_path = str(request.url.path)
    await log_and_broadcast(format_log(
        source="client_request", method="POST", url=url_path, request_payload=user.dict(exclude={'password'}) # Exclude pw from logs
    ))

    if user.username in users_db:
        response_payload = {"detail": "Username already registered"}
        await log_and_broadcast(format_log(
            source="server_response", method="POST", url=url_path, status=400, response_payload=response_payload
        ))
        raise HTTPException(status_code=400, detail="Username already registered")

    users_db[user.username] = user.password # Insecure: Store hashed passwords in real apps!
    response_payload = {"status": "success", "message": f"User '{user.username}' registered"}

    await log_and_broadcast(format_log(
        source="server_response", method="POST", url=url_path, status=200, response_payload=response_payload
    ))
    return response_payload

@app.post("/login/")
async def login_user(user: UserCredentials, request: Request):
    url_path = str(request.url.path)
    await log_and_broadcast(format_log(
        source="client_request", method="POST", url=url_path, request_payload=user.dict(exclude={'password'})
    ))

    stored_password = users_db.get(user.username)
    # Insecure: Compare plain text passwords. Use password hashing (e.g., passlib) in real apps!
    if not stored_password or stored_password != user.password:
        response_payload = {"detail": "Invalid username or password"}
        await log_and_broadcast(format_log(
            source="server_response", method="POST", url=url_path, status=401, response_payload=response_payload
        ))
        raise HTTPException(status_code=401, detail="Invalid username or password")

    response_payload = {"status": "success", "message": f"User '{user.username}' logged in"}
    await log_and_broadcast(format_log(
        source="server_response", method="POST", url=url_path, status=200, response_payload=response_payload
    ))
    return response_payload

@app.get("/user/{username}/")
async def get_user_info(username: str, request: Request):
    url_path = str(request.url.path)
    await log_and_broadcast(format_log(
        source="client_request", method="GET", url=url_path
    ))

    if username not in users_db:
        response_payload = {"detail": "User not found"}
        await log_and_broadcast(format_log(
            source="server_response", method="GET", url=url_path, status=404, response_payload=response_payload
        ))
        raise HTTPException(status_code=404, detail="User not found")

    # Return only safe info
    response_payload = {"username": username}
    await log_and_broadcast(format_log(
        source="server_response", method="GET", url=url_path, status=200, response_payload=response_payload
    ))
    return response_payload

@app.put("/user/{username}/")
async def update_user_password(username: str, update_data: UserUpdate, request: Request):
    url_path = str(request.url.path)
    await log_and_broadcast(format_log(
        source="client_request", method="PUT", url=url_path, request_payload={"username": username} # Don't log new pw
    ))

    if username not in users_db:
        response_payload = {"detail": "User not found"}
        await log_and_broadcast(format_log(
            source="server_response", method="PUT", url=url_path, status=404, response_payload=response_payload
        ))
        raise HTTPException(status_code=404, detail="User not found")

    users_db[username] = update_data.password # Update password (insecurely)
    response_payload = {"status": "success", "message": f"Password for user '{username}' updated"}
    await log_and_broadcast(format_log(
        source="server_response", method="PUT", url=url_path, status=200, response_payload=response_payload
    ))
    return response_payload

@app.post("/llm/generate")
async def generate_llm_response(payload: LLMPrompt, request: Request):
    url_path = str(request.url.path)
    client_request_payload = payload.dict()
    await log_and_broadcast(format_log(
        source="client_request", method="POST", url=url_path, request_payload=client_request_payload
    ))

    # --- Pseudo-Authentication Check ---
    if payload.username not in users_db:
        response_payload = {"detail": "User not found or not authenticated"}
        await log_and_broadcast(format_log(
            source="server_response", method="POST", url=url_path, status=401, response_payload=response_payload
        ))
        raise HTTPException(status_code=401, detail="User not found or not authenticated")

    # --- Call Ollama API ---
    ollama_url = "http://localhost:11434/api/generate"
    ollama_payload = {
        "model": "llama2", # Or your desired model
        "prompt": payload.prompt,
        "stream": False
    }

    async with httpx.AsyncClient(timeout=60.0) as client: # Increased timeout for LLM
        try:
            # Log the outgoing request to Ollama
            await log_and_broadcast(format_log(
                source="ollama_request", method="POST", url=ollama_url, request_payload=ollama_payload
            ))

            response = await client.post(ollama_url, json=ollama_payload)

            # Log the response from Ollama
            ollama_response_payload = None
            try:
                 # Try to parse JSON, but log raw if it fails
                ollama_response_payload = response.json()
            except json.JSONDecodeError:
                 ollama_response_payload = {"raw_response": response.text}

            await log_and_broadcast(format_log(
                source="ollama_response", url=ollama_url, status=response.status_code, response_payload=ollama_response_payload
            ))

            response.raise_for_status() # Raise exception for 4xx/5xx errors

            ollama_data = response.json()
            generated_text = ollama_data.get("response", "Error: No 'response' field found in Ollama output.")

            # Log the successful response being sent back to the client
            final_response_payload = {"text": generated_text}
            await log_and_broadcast(format_log(
                source="server_response", method="POST", url=url_path, status=200, response_payload=final_response_payload
            ))
            return final_response_payload

        except httpx.RequestError as exc:
            error_detail = f"Error requesting Ollama: {exc}"
            logger.error(error_detail)
            await log_and_broadcast(format_log(
                source="ollama_error", url=ollama_url, detail=error_detail
            ))
            await log_and_broadcast(format_log(
                source="server_response", method="POST", url=url_path, status=503, response_payload={"detail": "LLM service unavailable"}
            ))
            raise HTTPException(status_code=503, detail="LLM service unavailable")
        except httpx.HTTPStatusError as exc:
            error_detail = f"Ollama returned error: {exc.response.status_code} - {exc.response.text}"
            logger.error(error_detail)
            # Already logged the Ollama response, just log the server response error
            await log_and_broadcast(format_log(
                source="server_response", method="POST", url=url_path, status=502, response_payload={"detail": "Error from LLM service"}
            ))
            raise HTTPException(status_code=502, detail="Error from LLM service")
        except Exception as e:
             # Catch unexpected errors
            error_detail = f"Unexpected error during LLM generation: {e}"
            logger.exception(error_detail) # Log full traceback
            await log_and_broadcast(format_log(
                source="server_error", method="POST", url=url_path, detail=error_detail
            ))
            await log_and_broadcast(format_log(
                source="server_response", method="POST", url=url_path, status=500, response_payload={"detail": "Internal server error"}
            ))
            raise HTTPException(status_code=500, detail="Internal server error")

# --- Run Instruction (if running directly) ---
if __name__ == "__main__":
    import uvicorn
    # Make sure Ollama server is running (e.g., `ollama serve`)
    print("Ensure the Ollama server is running on http://localhost:11434")
    print("Starting FastAPI server on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
