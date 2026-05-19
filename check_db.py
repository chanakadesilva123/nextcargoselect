import os
import sqlalchemy as sa
DATABASE_URL = "postgresql+pg8000://root:SupermarketRAG123!@supermarket-au-db.ctiqc8668g4y.ap-southeast-2.rds.amazonaws.com:5432/postgres"
engine = sa.create_engine(DATABASE_URL)
with engine.connect() as conn:
    results = conn.execute(sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")).fetchall()
    print("Public tables:", results)
    results2 = conn.execute(sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema='rag'")).fetchall()
    print("RAG tables:", results2)
