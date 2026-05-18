import os
import urllib.parse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import sqlalchemy as sa

# Configure Gemini
os.environ["GOOGLE_API_KEY"] = "AIzaSyB6FfdaL5f-kd54VpdzKkDoS1sqdC7OwyM"
try:
    Settings.llm = Gemini(model="models/gemini-flash-latest")
except Exception as e:
    print(f"Failed to load Gemini model: {e}")
    Settings.llm = None

# Initialize Embedding Model (using standard 384-dim model to match PGVector)
Settings.embed_model = HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Setup Database connection for LlamaIndex
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@db:5432/ragdb")
parsed = urllib.parse.urlparse(DATABASE_URL)

try:
    vector_store = PGVectorStore.from_params(
        database=parsed.path[1:],
        host=parsed.hostname,
        password=parsed.password,
        port=parsed.port,
        user=parsed.username,
        table_name="supermarket_docs", # LlamaIndex appends 'data_' prefix -> 'data_supermarket_docs'
        schema_name="rag",
        embed_dim=384
    )
    index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
    
    # Use Chat Engine instead of Query Engine for conversational flow
    chat_engine = index.as_chat_engine(
        chat_mode="context",
        system_prompt=(
            "You are a professional, highly accurate Smart Assistant for a premium packaging and supermarket app. "
            "Your goal is to provide exceptional service to our customers. "
            "Always base your answers strictly on the provided context (our supermarket inventory). "
            "If a customer asks for a product that is not in the context, politely inform them that it is currently unavailable. "
            "When mentioning products, provide specific prices, brands, and categories if available. "
            "Provide practical, safe, and efficient packing advice when requested. "
            "Always be welcoming, polite, and professional in your tone. If the user greets you, greet them back warmly."
        )
    )
    query_engine = chat_engine # alias so the rest of the code works
except Exception as e:
    print(f"Error initializing LlamaIndex: {e}")
    query_engine = None

engine = sa.create_engine(DATABASE_URL)

import sys
sys.path.append(os.path.dirname(__file__))
import grpc
from concurrent import futures
import rag_pb2
import rag_pb2_grpc
import threading

class ProductService(rag_pb2_grpc.ProductServiceServicer):
    def GetProducts(self, request, context):
        try:
            import json
            with engine.connect() as conn:
                query_sql = sa.text('''
                    SELECT metadata_
                    FROM rag.data_supermarket_docs
                    WHERE embedding IS NOT NULL AND (is_enabled IS NULL OR is_enabled = true)
                    LIMIT 100
                ''')
                results = conn.execute(query_sql).fetchall()
                
            pb_products = []
            for i, r in enumerate(results):
                metadata = r[0] if isinstance(r[0], dict) else json.loads(r[0])
                
                price_str = metadata.get('price', '$0')
                if isinstance(price_str, str):
                    price_str = price_str.replace('$', '').strip()
                    try:
                        price = float(price_str)
                    except ValueError:
                        price = 0.0
                else:
                    price = float(price_str)
                    
                
                # Calculate size from dimensions (L * W), default to 100 if missing
                length = float(metadata.get('length', 10))
                width = float(metadata.get('width', 10))
                calc_size = length * width
                if calc_size <= 0: calc_size = 100.0
                    
                pb_products.append(rag_pb2.Product(
                    id=str(i + 1),
                    name=metadata.get('name', 'Unknown Product'),
                    price=price,
                    size=calc_size,
                    image=metadata.get('image_url', '/file.svg'),
                    shop=metadata.get('shop', 'N/A')
                ))
            return rag_pb2.ProductList(products=pb_products)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return rag_pb2.ProductList()

def serve_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    rag_pb2_grpc.add_ProductServiceServicer_to_server(ProductService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()

# Start gRPC server in background
grpc_thread = threading.Thread(target=serve_grpc, daemon=True)
grpc_thread.start()

app = FastAPI(title="SaaS RAG API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    query: str

@app.get("/")
def read_root():
    return {"message": "Welcome to Unified Master Architecture SaaS API"}

@app.get("/api/products")
def get_products(page: int = 1, limit: int = 50, category: str = None):
    try:
        import json
        offset = (page - 1) * limit
        
        where_clause = "WHERE embedding IS NOT NULL AND (is_enabled IS NULL OR is_enabled = true)"
        if category:
            safe_cat = category.replace("'", "''")
            where_clause += f" AND metadata_->>'category_l1' = '{safe_cat}'"
            
        with engine.connect() as conn:
            query_sql = sa.text(f'''
                SELECT id, metadata_
                FROM rag.data_supermarket_docs
                {where_clause}
                ORDER BY id ASC
                LIMIT {limit} OFFSET {offset}
            ''')
            results = conn.execute(query_sql).fetchall()
            
        products = []
        for i, r in enumerate(results):
            db_id = r[0]
            metadata = r[1] if isinstance(r[1], dict) else json.loads(r[1])
            
            # Extract price as float
            price_val = metadata.get('price')
            if price_val is None:
                price_val = '$0'
                
            if isinstance(price_val, str):
                price_val = price_val.replace('$', '').strip()
                try:
                    price = float(price_val)
                except ValueError:
                    price = 0.0
            else:
                try:
                    price = float(price_val)
                except (ValueError, TypeError):
                    price = 0.0
                
            
            length_val = metadata.get('length')
            width_val = metadata.get('width')
            
            try:
                length = float(length_val) if length_val is not None else 10.0
            except (ValueError, TypeError):
                length = 10.0
                
            try:
                width = float(width_val) if width_val is not None else 10.0
            except (ValueError, TypeError):
                width = 10.0
                
            calc_size = length * width
            if calc_size <= 0: calc_size = 100.0
            
            products.append({
                "id": str(db_id),
                "name": metadata.get('name', 'Unknown Product'),
                "price": price,
                "size": calc_size,
                "image": metadata.get('image_url', '/file.svg'),
                "shop": metadata.get('shop', 'N/A'),
                "category": metadata.get('category_l1', 'Uncategorized')
            })
        return products
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/chat")
def chat(request: ChatRequest):
    if query_engine is None:
        return {"response": "Error: RAG Engine is not initialized properly."}
        
    try:
        response = query_engine.chat(request.query)
        return {"response": str(response)}
    except Exception as e:
        return {"response": f"Error during query: {str(e)}"}
