import os
import re
import uuid
import pickle
from langchain_chroma import Chroma
from langchain.storage import LocalFileStore
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.retrievers import BM25Retriever
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_PATH = ".\model\Embedding Model"
RERANK_MODEL_PATH = ".\model\Rerank Model"
DATA_PATH = ".\data\Literature"
DATABASE_PATH = ".\data\ChromaDB_Standard"
BM25_INDEX_FOLDER = ".\data\BM25Index"
DOCSTORE_PATH = ".\data\DocStore"

model_name = "Qwen/Qwen3-Embedding-0.6B"
model = SentenceTransformer(model_name)
model.save(EMBEDDING_MODEL_PATH)

model_name = "BAAI/bge-reranker-v2-m3"
model = SentenceTransformer(model_name)
model.save(RERANK_MODEL_PATH)

embedding_model = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL_PATH,
    model_kwargs={'device': 'cuda'},
    encode_kwargs={'batch_size': 2}
)

loader = DirectoryLoader(
    DATA_PATH, 
    glob="**/*.md", 
    use_multithreading=True,
    loader_cls=TextLoader,
    loader_kwargs={"encoding": "utf-8"}
)
documents = loader.load()

code_docs, test_docs = [], []

for doc in documents:
    file_name = doc.metadata.get("source", "").lower()
    if "code" in file_name:
        code_docs.append(doc)
    else:
        test_docs.append(doc)


all_chunks = []
parent_docstore = LocalFileStore(DOCSTORE_PATH)

headers = [("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3"), ("####", "Header 4"), ("#####", "Header 5")]
markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers)

if code_docs:
    for doc in code_docs:
        splits = markdown_splitter.split_text(doc.page_content)
        file_name = doc.metadata.get("source", "").split(os.path.sep)[-1].lower()
    
        for split in splits:
            split.metadata["file_name"] = file_name
            split.metadata["doc_type"] = "HK Code"
            split.metadata["method_id"] = "N/A"
        
        all_chunks.extend(splits)

if test_docs:
    parent_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "H1")])
    parent_chunks_store = []

    for doc in test_docs:
        parent_chunks = parent_splitter.split_text(doc.page_content)
        child_chunks = markdown_splitter.split_text(doc.page_content)
        file_name = doc.metadata.get("source", "").split(os.path.sep)[-1].lower()

        method_id_match = re.search(r"[A-Z]\d+", file_name, re.IGNORECASE)
        method_id = method_id_match.group(0) if method_id_match else "N/A"

        for parent_chunk in parent_chunks:
            parent_id = str(uuid.uuid4())
            parent_chunk.metadata["doc_id"] = parent_id
            parent_chunks_store.append((parent_id, pickle.dumps(parent_chunk)))

            for child_chunk in child_chunks:
                if child_chunk.page_content in parent_chunk.page_content:
                    child_chunk.metadata["parent_id"] = parent_id
                    child_chunk.metadata["file_name"] = file_name
                    child_chunk.metadata["doc_type"] = "ASTM Test"
                    child_chunk.metadata["method_id"] = method_id
                    all_chunks.append(child_chunk)

    if parent_chunks_store:
        parent_docstore.mset(parent_chunks_store)


vectorstore = Chroma.from_documents(
    documents=all_chunks,
    embedding=embedding_model,
    persist_directory=DATABASE_PATH
    )


bm25_retriever = BM25Retriever.from_documents(all_chunks, k=5)
with open(BM25_INDEX_FOLDER, "wb") as f:
        pickle.dump(bm25_retriever, f)