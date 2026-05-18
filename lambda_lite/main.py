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
def get_products(page: int = 1, limit: int = 50):
    try:
        import json
        offset = (page - 1) * limit
        with engine.connect() as conn:
            query_sql = sa.text(f'''
                SELECT id, metadata_
                FROM rag.data_supermarket_docs
                WHERE embedding IS NOT NULL AND (is_enabled IS NULL OR is_enabled = true)
                ORDER BY id ASC
                LIMIT {limit} OFFSET {offset}
            ''')
            results = conn.execute(query_sql).fetchall()
            
        products = []
        for i, r in enumerate(results):
            db_id = r[0]
            metadata = r[1] if isinstance(r[1], dict) else json.loads(r[1])
            
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

handler = Mangum(app)
