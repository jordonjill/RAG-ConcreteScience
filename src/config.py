
class Config:
    # Server Configuration
    HOST = "0.0.0.0"  # Use "127.0.0.1" for localhost only
    PORT = 8000
    
    # Security - IMPORTANT: Change this in production!
    API_KEY = "123"
    
    # Ollama Configuration
    OLLAMA_BASE_URL = "http://localhost:11434"
    OLLAMA_MODEL = "llama3.1:8b"
    OLLAMA_API_KEY = "ollama"
    
    # Model Paths (relative to project root)
    EMBEDDING_MODEL_PATH = r".\model\Embedding Model"
    RERANK_MODEL_PATH = r".\model\Rerank Model"
    
    # Data Paths (relative to project root)
    DATA_PATH = r".\data\Literature"
    DATABASE_PATH = r".\data\ChromaDB_Standard"
    BM25_INDEX_FOLDER = r".\data\BM25Index"
    DOCSTORE_PATH = r".\data\DocStore"