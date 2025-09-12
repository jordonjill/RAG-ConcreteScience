# RAG-Based Question Answering System for Concrete Materials and Test Standards

A sophisticated Retrieval-Augmented Generation (RAG) system designed for technical document analysis and question-answering, specifically built for concrete materials and civil engineering standards (HK Concrete Code and Some Test Standards).

## Features

- **Advanced RAG Architecture**: Multi-stage retrieval with BM25 and vector search
- **Agent-Based Processing**: LangGraph-powered AI agent with tool selection
- **Dual Retrieval Systems**: Self-query and ensemble retrievers for different query types  
- **Real-time Streaming**: Server-sent events for live response streaming
- **Interactive Web Interface**: Modern React-like frontend with real-time chat
- **Document Reranking**: Cross-encoder reranking for improved relevance
- **Persistent Memory**: Conversation history with thread management
- **Authentication**: API key-based security
- **Health Monitoring**: Service status and model health checks

## Architecture

### Backend Stack
- **FastAPI**: High-performance web framework for API endpoints
- **LangChain**: Framework for building LLM applications with retrievers and chains
- **LangGraph**: State machine-based agent orchestration with tool calling
- **ChromaDB**: Vector database for semantic search
- **BM25**: Traditional keyword-based retrieval for hybrid search
- **Ollama**: Local LLM inference engine
- **HuggingFace**: Embedding and reranking model integration

### Frontend Stack
- **Server-Sent Events (SSE)**: Real-time streaming responses
- **MathJax**: LaTeX equation rendering support
- **Font Awesome**: Icon library integration

### ML Components
- **Embedding Model**: Qwen3-Embedding-0.6B for semantic vector generation
- **Reranking Model**: BAAI/bge-reranker-v2-m3 for result refinement
- **Language Model**: Llama 3.1 8B via Ollama for response generation

## System Design

### RAG Pipeline
```
Query → Agent Router → Tool Selection → Retrieval → Reranking → Context Assembly → LLM Generation → Streaming Response
```

1. **Agent Router**: Determines whether to use self-query or ensemble retrieval
2. **Self-Query Retrieval**: For specific test method ID queries (e.g., "ASTM C157")
3. **Ensemble Retrieval**: For general technical questions (combines BM25 + vector search)
4. **Cross-Encoder Reranking**: Improves retrieval relevance with top-k selection
5. **Parent Document Retrieval**: Fetches full documents from compressed chunks
6. **LLM Generation**: Context-aware response generation with conversation memory

## Prerequisites

- Python 3.8+
- Ollama installed and running
- CUDA-capable GPU
- 8GB+ RAM for model loading

## Usage Examples

### Technical Queries
```
"What are the effects of alkali-silica reaction in concrete?"
"How to perform a slump test according to standards?"
"Explain the durability factors affecting concrete structures"
```

### Specific Test Methods
```
"What is ASTM C157 about?"
"Show me the procedure for ASTM C157"
"Find information about test method C157"
```

The system automatically routes queries to the appropriate retrieval method based on content analysis.

## Project Structure

```
├── src/
│   ├── main.py                 # FastAPI application entry point
│   ├── rag_service.py          # Core RAG implementation with LangGraph
│   ├── database.py             # Database initialization and model setup
│   ├── config.py               # Configuration management
│   └── static/
│       ├── index.html          # Web interface
│       ├── script.js           # Frontend JavaScript
│       └── style.css           # UI styling
├── data/                       # Data storage and indices
├── model/                      # Downloaded AI models
├── README.md                   # This file
└── requirements.txt            # Python dependencies
```
