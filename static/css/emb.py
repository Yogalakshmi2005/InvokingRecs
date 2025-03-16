from pymongo import MongoClient
import numpy as np
import os
from sentence_transformers import SentenceTransformer

# Load local MiniLM model
MODEL_PATH = os.path.join("model_cache", "models--sentence-transformers--all-MiniLM-L6-v2")
embedding_model = SentenceTransformer(MODEL_PATH)

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["InvokesDB"]
books_collection = db["books"]

# Process each book and add embeddings
for book in books_collection.find():
    if "embedding" not in book:  # Avoid duplicate processing
        text = book.get("description", "")  # Use description as book context
        book_embedding = embedding_model.encode([text])[0].tolist()  # Convert to list for MongoDB storage

        books_collection.update_one(
            {"_id": book["_id"]}, {"$set": {"embedding": book_embedding}}
        )

print("✅ Embeddings added successfully!")
