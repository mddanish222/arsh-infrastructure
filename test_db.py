import os
from dotenv import load_dotenv
import psycopg2

print("1. Starting program")

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

print("2. DATABASE_URL loaded:", DATABASE_URL is not None)

try:
    print("3. Trying to connect...")
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    print("✅ Database connected successfully!")
    conn.close()
except Exception as e:
    print("❌ Connection failed:")
    print(repr(e))

print("4. Program finished")