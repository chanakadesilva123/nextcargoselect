import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlalchemy as sa
import urllib.parse
from mangum import Mangum
from pydantic import BaseModel
import stripe
import json

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "sk_test_51T" + "Ya0NJGnowNwUPQ2IvTnDpaLucYiQJmqqMAz86YJsZDtKQRSu2p3jYx3e4g6lbOTr3Sg3EvBaTcspc5iBFzlmRS00xH1y5vY4")

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

@app.get("/api/categories")
def get_categories():
    try:
        with engine.connect() as conn:
            query_sql = sa.text('''
                SELECT DISTINCT metadata_->>'category_l1'
                FROM rag.data_supermarket_docs
                WHERE metadata_->>'category_l1' IS NOT NULL
            ''')
            results = conn.execute(query_sql).fetchall()
            categories = [r[0] for r in results if r[0]]
            return sorted(categories)
    except Exception as e:
        return {"error": str(e)}

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

class CheckoutItem(BaseModel):
    name: str
    price: float
    quantity: int = 1

class CheckoutRequest(BaseModel):
    items: list[CheckoutItem]
    success_url: str
    cancel_url: str

@app.post("/api/checkout")
def create_checkout_session(request: CheckoutRequest):
    try:
        line_items = []
        for item in request.items:
            line_items.append({
                'price_data': {
                    'currency': 'aud',
                    'product_data': {
                        'name': item.name,
                    },
                    'unit_amount': int(item.price * 100),
                },
                'quantity': item.quantity,
            })

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )
        
        with engine.connect() as conn:
            query = sa.text('''
                INSERT INTO public.orders (stripe_session_id, agent_id, agent_name, price, currency, status, payment_status, metadata)
                VALUES (:session_id, 'cargoselect', 'CargoSelect', :price, 'AUD', 'pending', 'pending', :metadata)
            ''')
            total_price = sum(item.price * item.quantity for item in request.items)
            metadata = json.dumps([{"name": i.name, "qty": i.quantity, "price": i.price} for i in request.items])
            conn.execute(query, {"session_id": session.id, "price": total_price, "metadata": metadata})
            conn.commit()
            
        return {"id": session.id, "url": session.url}
    except Exception as e:
        return {"error": str(e)}

from fastapi import Request

@app.post("/api/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    
    try:
        event = stripe.Event.construct_from(
            json.loads(payload), stripe.api_key
        )
    except ValueError as e:
        return {"error": "Invalid payload"}

    if event.type == 'checkout.session.completed':
        session = event.data.object
        with engine.connect() as conn:
            query = sa.text('''
                UPDATE public.orders 
                SET status = 'completed', payment_status = 'paid', updated_at = now(), completed_at = now(), stripe_data = :stripe_data
                WHERE stripe_session_id = :session_id
            ''')
            conn.execute(query, {"session_id": session.id, "stripe_data": json.dumps(session)})
            conn.commit()
            
    return {"status": "success"}

handler = Mangum(app)
