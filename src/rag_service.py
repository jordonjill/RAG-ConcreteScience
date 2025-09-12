import pickle
import time
from typing import Dict, Any, Generator
from langchain_core.tools import tool
from langchain.retrievers import EnsembleRetriever
from langchain.chains.query_constructor.base import AttributeInfo
from langchain.retrievers.self_query.base import SelfQueryRetriever
from langchain_chroma import Chroma
from langchain.retrievers import ContextualCompressionRetriever
from langchain_ollama.chat_models import ChatOllama
from langchain.schema import BaseRetriever
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.runnables import RunnableLambda
from langchain.storage import LocalFileStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langgraph.graph import StateGraph, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver


class RAGService:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._load_models()
        self._setup_retrievers()
        self._setup_agent()
        
    def _load_models(self):
        """Load all models"""
        try:
            self.embedding_model = HuggingFaceEmbeddings(model_name=self.config["embedding_model_path"])

            self.rerank_model = HuggingFaceCrossEncoder(model_name=self.config["rerank_model_path"])
            
            self.llm = ChatOllama(
                    model=self.config.get("ollama_model", "llama3.1:8b"), 
                    seed=42, 
                    temperature=0.5,
                )
            
            self.vectorstore = Chroma(
                persist_directory=self.config["database_path"],
                embedding_function=self.embedding_model
            )

            self.parent_docstore = LocalFileStore(self.config["docstore_path"])
            
        except Exception as e:
            print(f"Model loading failed: {e}")
            raise
    
    def _setup_retrievers(self):
        try:
            self.metadata_info = [
                AttributeInfo(
                    name="doc_type",
                    description="The type of the document, for example, 'ASTM Test' or 'HK Code'",
                    type="string",
                ),
                AttributeInfo(
                    name="method_id",
                    description="The unique identifier for the test method, such as 'c157' or 'c109', MUST be in lowercase",
                    type="string",
                ),
            ]
            # Retriever 1
            self.vector_retriever = SelfQueryRetriever.from_llm(
                llm=self.llm,
                vectorstore=self.vectorstore,
                document_contents="Standard test methods for concrete materials and Hong Kong concrete code for civil engineering",
                metadata_field_info=self.metadata_info,
                verbose = False,
            )

            # Retriever 2
            self.base_vector_retriever = self.vectorstore.as_retriever(search_kwargs={"k": 5})

            with open(self.config["bm25_index_folder"], "rb") as f:
                self.bm25_retriever = pickle.load(f)

            self.ensemble_retriever = EnsembleRetriever(
                retrievers=[self.bm25_retriever, self.base_vector_retriever],
                weights=[0.5, 0.5]
            )

            self.reranker = CrossEncoderReranker(model=self.rerank_model, top_n=5)
            
        except Exception as e:
            print(f"Retrievers setup failed: {e}")
            raise
    
    def _get_final_context(self, retrieved_docs):
        final_context_docs = []
        parent_ids_to_fetch = [doc.metadata["parent_id"] for doc in retrieved_docs if "parent_id" in doc.metadata]
        
        if parent_ids_to_fetch:
            byte_values = self.parent_docstore.mget(parent_ids_to_fetch)
            parent_docs_objects = [pickle.loads(b) for b in byte_values if b is not None]
            parents_map = {doc.metadata["doc_id"]: doc for doc in parent_docs_objects}
        else:
            parents_map = {}

        for doc in retrieved_docs:
            if "parent_id" in doc.metadata:
                parent = parents_map.get(doc.metadata["parent_id"])
                if parent:
                    final_context_docs.append(parent)
            else:
                final_context_docs.append(doc)
                
        return "\n\n---\n\n".join([doc.page_content for doc in final_context_docs])

    def _create_retrieval_chain(self, retriever: BaseRetriever):
        compression_retriever = ContextualCompressionRetriever(
            base_compressor=self.reranker, 
            base_retriever=retriever
        )
        retrieval_chain = compression_retriever | RunnableLambda(self._get_final_context)
        return retrieval_chain
    
    def _setup_agent(self):
        try:
            self.self_query_chain = self._create_retrieval_chain(self.vector_retriever)
            self.ensemble_chain = self._create_retrieval_chain(self.ensemble_retriever)

            @tool
            def self_query_search(query: str):
                """Use this tool ONLY when the user's query explicitly mentions a specific test method ID (e.g., 'C157', 'ASTM C109', 'c109').
                This tool precisely locates the standard test method document based on its ID."""
                return self.self_query_chain.invoke(query)

            @tool
            def ensemble_search(query: str):
                """Use this tool for technical questions about concrete materials, material durability, or engineering specifications
                when NO specific method ID is mentioned. For example: 'What are the effects of alkali-silica reaction?'
                or 'How to perform a slump test?'.
                """
                return self.ensemble_chain.invoke(query)

            self.tools = [self_query_search, ensemble_search]

            def planner_node(state: MessagesState):
                llm_with_tools = self.llm.bind_tools(self.tools)
                response = llm_with_tools.invoke(state['messages'])
                return {"messages": [response]}

            def generate_node(state: MessagesState):
                """Generate answer."""
                recent_tool_messages = []
                for message in reversed(state["messages"]):
                    if message.type == "tool":
                        recent_tool_messages.append(message)
                    else:
                        break
                        
                tool_messages = recent_tool_messages[::-1]
                docs_content = "\n\n".join(msg.content for msg in tool_messages)
                system_prompt = (
                    "You are an assistant for question-answering tasks. "
                    "Use the following pieces of retrieved context to answer "
                    "the question. If you don't know the answer, say that you "
                    "don't know."
                    "\n\n"
                    f"{docs_content}"
                )
                
                conversation_messages = [
                    message
                    for message in state["messages"]
                    if message.type in ("human", "system")
                    or (message.type == "ai" and not message.tool_calls)
                ]
                
                prompt = [SystemMessage(system_prompt)] + conversation_messages
                
                response = self.llm.invoke(prompt)
                return {"messages": [response]}

            # Build workflow
            self.tools_node = ToolNode(self.tools)
            
            workflow = StateGraph(MessagesState)
            workflow.add_node("planner", planner_node)
            workflow.add_node("tools", self.tools_node)
            workflow.add_node("generator", generate_node)

            workflow.set_entry_point("planner")

            workflow.add_conditional_edges(
                "planner",
                tools_condition,
                {
                    "tools": "tools", 
                    END: END,
                },
            )
            workflow.add_edge("tools", "generator")
            workflow.add_edge("generator", END)

            self.memory = MemorySaver()
            self.app = workflow.compile(checkpointer=self.memory)
            
        except Exception as e:
            print(f"Agent setup failed: {e}")
            raise
    
    def get_response(self, query: str, conversation_id: str = None) -> Generator [Dict[str, Any], None, None]:
        try:
            if not conversation_id:
                conversation_id = f"thread_{int(time.time())}"
            
            config = {"configurable": {"thread_id": conversation_id}}

            current_input = [HumanMessage(content=query)]

            for message, _ in self.app.stream(
                {"messages": current_input},
                stream_mode="messages",
                config=config,
            ):
                if isinstance(message, AIMessage) and not message.tool_calls:
                    if message.content:
                        yield {
                            "response_chunk": message.content, 
                            "type": "content",
                            "conversation_id": conversation_id
                        }

        except Exception as e:
            yield {
                "response_chunk": f"Error occurred while processing query: {str(e)}",
                "conversation_id": conversation_id or f"thread_{int(time.time())}",
                "type": "error"
            }
    
    def health_check(self) -> Dict[str, Any]:

        try:
            test_response = self.llm.invoke([HumanMessage(content="test")])
            return {
                "status": "healthy",
                "models_loaded": True,
                "message": "RAG service is running properly"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "models_loaded": False,
                "message": f"RAG service error: {str(e)}"
            }
