from pathlib import Path
from dotenv import load_dotenv
import os
from pymongo import MongoClient

# Load .env
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.getenv("MONGO_URL")

# Mask password for display
if mongo_url and "@" in mongo_url:
    prefix = mongo_url.split("@")[0]
    suffix = mongo_url.split("@")[1]
    if ":" in prefix:
        user = prefix.split(":")[1].replace("//", "")
        masked_url = f"mongodb+srv://{user}:******@{suffix}"
    else:
        masked_url = mongo_url
else:
    masked_url = mongo_url

print("==================================================")
print("1. LOADED MONGO_URL:", masked_url)
print("2. DB_NAME:", os.getenv("DB_NAME"))
print("==================================================")

print("3. TESTING MONGO CONNECTION...")
client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)

try:
    info = client.admin.command("ping")
    print("SUCCESS: Connected to MongoDB successfully!")
    print("Ping response:", info)
except Exception as e:
    print("FAILED: Connection error details:")
    print(type(e).__name__, ":", e)
print("==================================================")
