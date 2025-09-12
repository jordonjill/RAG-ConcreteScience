from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, Dict, Any
import time
import asyncio
import logging
import json
from contextlib import asynccontextmanager

from rag_service import RAGService
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    processing_time: float
    status: str

class HealthResponse(BaseModel):
    status: str
    models_loaded: bool
    message: str
    timestamp: float

# Global variables
rag_service: Optional[RAGService] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_service

    try:
        config_dict = {
            "host": Config.HOST,
            "port": Config.PORT,
            "api_key": Config.API_KEY,
            "ollama_base_url": Config.OLLAMA_BASE_URL,
            "ollama_model": Config.OLLAMA_MODEL,
            "ollama_api_key": Config.OLLAMA_API_KEY,
            "embedding_model_path": Config.EMBEDDING_MODEL_PATH,
            "database_path": Config.DATABASE_PATH,
            "bm25_index_folder": Config.BM25_INDEX_FOLDER,
            "docstore_path": Config.DOCSTORE_PATH,
            "rerank_model_path": Config.RERANK_MODEL_PATH
        }
        rag_service = RAGService(config_dict)

        logger.info("RAG service initialization completed successfully")

    except Exception as e:
        logger.error(f"RAG service initialization failed: {e}")
        rag_service = None
    
    yield
    logger.info("Shutting down RAG service...")

app = FastAPI(
    title="RAG System",
    description="RAG-based Question Answering System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if credentials.credentials != Config.API_KEY:
        logger.warning(f"Invalid API key attempt: {credentials.credentials}...")

        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return credentials.credentials

@app.get("/", response_class=HTMLResponse)
async def read_root():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            html_content = f.read()

        return HTMLResponse(content=html_content)
    
    except FileNotFoundError:
        logger.error("Frontend HTML file not found")

        raise HTTPException(
            status_code=404,
            detail="Frontend page not found"
        )

@app.get("/health", response_model=HealthResponse)
async def health_check():

    global rag_service
    
    if rag_service is None:
        return HealthResponse(
            status="unhealthy",
            models_loaded=False,
            message="RAG service not initialized",
            timestamp=time.time()
        )
    
    try:
        health_result = rag_service.health_check()
        return HealthResponse(
            status=health_result["status"],
            models_loaded=health_result["models_loaded"],
            message=health_result["message"],
            timestamp=time.time()
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            models_loaded=False,
            message=f"Health check error: {str(e)}",
            timestamp=time.time()
        )

@app.post("/chat")
async def chat_stream(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    global rag_service
    
    if rag_service is None:
        raise HTTPException(
            status_code=503,
            detail="RAG service unavailable"
        )
    
    if not request.query.strip():
        raise HTTPException(
            status_code=400,
            detail="Query content cannot be empty"
        )

    async def generate_response():
        try:
            logger.info(f"Processing streaming chat request: query_length={len(request.query)}")
            start_time = time.time()
            conversation_id = request.conversation_id or f"thread_{int(time.time())}"

            response_generator = rag_service.get_response(request.query, conversation_id)

            for chunk in response_generator:
                if chunk.get("type") == "content":
                    chunk["conversation_id"] = conversation_id
                    yield f"data: {json.dumps(chunk)}\n\n"
                    await asyncio.sleep(0)

                elif chunk.get("type") == "error":
                    chunk["conversation_id"] = conversation_id
                    yield f"data: {json.dumps(chunk)}\n\n"
                    break

            processing_time = time.time() - start_time
            final_chunk = {
                "type": "done",
                "conversation_id": conversation_id,
                "processing_time": processing_time,
                "status": "completed"
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"

            logger.info(f"Streaming chat request completed in {processing_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Streaming chat request processing failed: {e}")
            error_chunk = {
                "type": "error",
                "response_chunk": f"Failed to process chat request: {str(e)}",
                "conversation_id": request.conversation_id or f"thread_{int(time.time())}",
                "status": "error"
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"

    return StreamingResponse(
        generate_response(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/plain; charset=utf-8",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/config")
async def get_config_endpoint(api_key: str = Depends(verify_api_key)) -> Dict[str, Any]:
    safe_config = {
        "ollama_model": Config.OLLAMA_MODEL,
        "ollama_base_url": Config.OLLAMA_BASE_URL,
        "host": Config.HOST,
        "port": Config.PORT,
    }
    
    return safe_config

@app.post("/update-config")
async def update_config_endpoint(new_config: Dict[str, Any], api_key: str = Depends(verify_api_key)) -> Dict[str, str]:
    try:
        logger.info(f"Configuration update requested (restart required to take effect)")
        return {"message": "Configuration noted. Please manually update config.py and restart service."}

    except Exception as e:
        logger.error(f"Configuration update failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Configuration update failed: {str(e)}"
        )

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":

    import uvicorn
    logger.info(f"Starting server: http://{Config.HOST}:{Config.PORT}")
    logger.info(f"API Key: {Config.API_KEY}")
    logger.info(f"Ollama Model: {Config.OLLAMA_MODEL}")
    logger.info(f"Ollama Base URL: {Config.OLLAMA_BASE_URL}")
    
    if Config.API_KEY == "123":
        logger.warning("Using default API key. Please change it in production!")
    
    # Start the server
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=False,
        log_level="info"
    )
