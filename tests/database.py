from sqlalchemy import create_engine

engine = create_engine("postgresql+psycopg2://postgres:postgres@localhost:5432/ai_db")

with engine.connect() as conn:
    print("Database connected successfully")