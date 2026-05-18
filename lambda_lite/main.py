import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlalchemy as sa
import urllib.parse
from mangum import Mangum

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+pg8000://root:SupermarketRAG123!@supermarket-au-db.ctiqc8668g4y.ap-southeast-2.rds.amazonaws.com:5432/postgres")
engine = sa.create_engine(DATABASE_URL)

app = FastAPI(title="SaaS RAG API - Lite", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to Unified Master Architecture SaaS API (Lambda Edition)"}

@app.get("/api/products")
def get_products():
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
            
        products = []
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
            
            length = float(metadata.get('length', 10))
            width = float(metadata.get('width', 10))
            calc_size = length * width
            if calc_size <= 0: calc_size = 100.0
            
            products.append({
                "id": str(i + 1),
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

handler = Mangum(app)
