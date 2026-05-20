import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlalchemy as sa
import urllib.parse
from mangum import Mangum
from pydantic import BaseModel
import stripe
import json
import random
from datetime import datetime, timedelta

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

@app.get("/api/boxes")
def get_boxes():
    try:
        with engine.connect() as conn:
            query_sql = sa.text('SELECT * FROM rag.shipping_boxes WHERE is_enabled = true ORDER BY id ASC')
            results = conn.execute(query_sql).fetchall()
            boxes = []
            for r in results:
                boxes.append({
                    "id": r[0],
                    "name": r[1],
                    "price": float(r[2]),
                    "length_cm": r[3],
                    "width_cm": r[4],
                    "height_cm": r[5],
                    "is_enabled": r[6]
                })
            return boxes
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/routes")
def get_routes():
    try:
        with engine.connect() as conn:
            orig_sql = sa.text('SELECT * FROM rag.shipping_route_origins WHERE is_enabled = true ORDER BY id ASC')
            dest_sql = sa.text('SELECT * FROM rag.shipping_route_destinations WHERE is_enabled = true ORDER BY id ASC')
            
            orig_results = conn.execute(orig_sql).fetchall()
            dest_results = conn.execute(dest_sql).fetchall()
            
            origins = [{"id": r[0], "label": r[1], "code": r[2], "port": r[3], "is_enabled": r[4]} for r in orig_results]
            destinations = [{"id": r[0], "label": r[1], "code": r[2], "port": r[3], "is_enabled": r[4]} for r in dest_results]
            
            return {"origins": origins, "destinations": destinations}
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
    customer_name: str = None
    customer_email: str = None
    customer_phone: str = None

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

        session_params = {
            'payment_method_types': ['card'],
            'line_items': line_items,
            'mode': 'payment',
            'success_url': request.success_url,
            'cancel_url': request.cancel_url,
        }
        if request.customer_email:
            session_params['customer_email'] = request.customer_email

        session = stripe.checkout.Session.create(**session_params)
        
        with engine.connect() as conn:
            query = sa.text('''
                INSERT INTO public.orders (stripe_session_id, agent_id, agent_name, price, currency, status, payment_status, metadata)
                VALUES (:session_id, 'cargoselect', 'CargoSelect', :price, 'AUD', 'pending', 'pending', :metadata)
            ''')
            total_price = sum(item.price * item.quantity for item in request.items)
            metadata_dict = {
                "items": [{"name": i.name, "qty": i.quantity, "price": i.price} for i in request.items],
                "customer_name": request.customer_name,
                "customer_email": request.customer_email,
                "customer_phone": request.customer_phone
            }
            metadata = json.dumps(metadata_dict)
            conn.execute(query, {"session_id": session.id, "price": total_price, "metadata": metadata})
            conn.commit()
            
        return {"id": session.id, "url": session.url}
    except Exception as e:
        return {"error": str(e)}

from fastapi import Request

@app.get("/api/orders/{session_id}")
def get_order_by_session(session_id: str):
    try:
        with engine.connect() as conn:
            query = sa.text('SELECT id, status, payment_status, price FROM public.orders WHERE stripe_session_id = :session_id LIMIT 1')
            result = conn.execute(query, {"session_id": session_id}).fetchone()
            if result:
                return {"id": result[0], "status": result[1], "payment_status": result[2], "price": float(result[3])}
            return {"error": "Order not found"}
    except Exception as e:
        return {"error": str(e)}

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

class SendOtpRequest(BaseModel):
    identifier: str

class VerifyOtpRequest(BaseModel):
    identifier: str
    code: str

@app.post("/api/auth/send-otp")
def send_otp(request: SendOtpRequest):
    try:
        otp = str(random.randint(100000, 999999))
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        with engine.connect() as conn:
            query = sa.text('''
                INSERT INTO public.otp_codes (identifier, code, expires_at)
                VALUES (:identifier, :code, :expires_at)
            ''')
            conn.execute(query, {"identifier": request.identifier, "code": otp, "expires_at": expires_at})
            conn.commit()
            
        return {"status": "success", "message": "OTP sent successfully.", "mock_otp": otp}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/auth/verify-otp")
def verify_otp(request: VerifyOtpRequest):
    try:
        with engine.connect() as conn:
            query = sa.text('''
                SELECT id FROM public.otp_codes 
                WHERE identifier = :identifier AND code = :code AND expires_at > NOW()
                ORDER BY created_at DESC LIMIT 1
            ''')
            result = conn.execute(query, {"identifier": request.identifier, "code": request.code}).fetchone()
            
            if result:
                user_query = sa.text("SELECT id, name, email FROM public.users WHERE email = :identifier OR phone_number = :identifier LIMIT 1")
                user = conn.execute(user_query, {"identifier": request.identifier}).fetchone()
                
                if not user:
                    insert_user = sa.text('''
                        INSERT INTO public.users (name, email, password_hash)
                        VALUES (:name, :email, 'otp_login') RETURNING id, name, email
                    ''')
                    name = request.identifier.split('@')[0]
                    email = request.identifier if '@' in request.identifier else f"{request.identifier}@example.com"
                    user = conn.execute(insert_user, {"name": name, "email": email}).fetchone()
                    conn.commit()
                
                del_query = sa.text("DELETE FROM public.otp_codes WHERE identifier = :identifier")
                conn.execute(del_query, {"identifier": request.identifier})
                conn.commit()
                
                return {
                    "status": "success", 
                    "user": {"id": user[0], "name": user[1], "email": user[2]}
                }
            else:
                return {"error": "Invalid or expired OTP."}
    except Exception as e:
        return {"error": str(e)}

handler = Mangum(app)
