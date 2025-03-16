from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_cors import CORS
import os
from bson import ObjectId
from bson.errors import InvalidId
import requests

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


app.config["MONGO_URI"] = "mongodb://localhost:27017/InvokesDB"
mongo = PyMongo(app)
books_collection = mongo.db.books
users_collection = mongo.db.users

try:
    mongo.db.command("ping")
    print("Connected to MongoDB Successfully!")
except Exception as e:
    print("MongoDB Connection Error:", e)

bcrypt = Bcrypt(app)

# Flask-Login Configuration
login_manager = LoginManager()
login_manager.login_view = "form"
login_manager.init_app(app)

# User Model for Flask-Login
class User(UserMixin):
    def __init__(self, user_id, email):
        self.id = user_id
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if user:
        return User(str(user["_id"]), email=user["email"])
    return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/form')
def form():
    return render_template('form.html')

@app.route('/signup', methods=['POST'])
def signup():
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')

    existing_user = users_collection.find_one({"email": email})
    if existing_user:
        flash("Email already registered! Please login.", "warning")
        return redirect(url_for("form"))

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    users_collection.insert_one({"name": name, "email": email, "password": hashed_password})

    flash("Account created successfully! Please log in.", "info")
    return redirect(url_for("form"))

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')

    user = users_collection.find_one({"email": email})
    if user and bcrypt.check_password_hash(user["password"], password):
        session["user_email"] = email  # Store email in session
        flash("Login successful!", "success")
        return redirect(url_for("recommendation"))

    flash("Invalid credentials!", "danger")
    return redirect(url_for("form"))

@app.route('/recommendation', methods=['GET'])
def recommendation():
    if "user_email" in session:
        return render_template('recommendation.html', email=session["user_email"])
    else:
        flash("Please log in first!", "warning")
        return redirect(url_for("form"))

@app.route('/logout')
def logout():
    session.pop("user_email", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("form"))

@app.route("/chatbot")
def chatbot():
    return render_template("chatbot.html")

@app.route("/api/chatbot", methods=["POST"])
def chatbot_api():
    data = request.json
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"response": "Please enter a valid message."})

    # Step 1️⃣: Retrieve books related to user query from MongoDB
    books = books_collection.find({
        "$or": [
            {"title": {"$regex": user_message, "$options": "i"}},
            {"description": {"$regex": user_message, "$options": "i"}}
        ]
    })

    book_list = list(books)[:5]  # Limit results to 5 books

    if not book_list:
        context = "No books found, but you can ask me about other topics!"
    else:
        context = "Here are some related books:\n"
        for book in book_list:
            context += f"- {book.get('title', 'Unknown')} by {book.get('author', 'Unknown')}\n"

    # Step 2️⃣: Send data to Groq AI for enhanced response
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "messages": [
            {"role": "system",
             "content": "You are a self-help book assistant. Keep responses concise unless the user explicitly asks for details."},
            {"role": "user", "content": user_message}
        ],
        "model": "mixtral-8x7b-32768",
        "temperature": 0.7
    }

    response = requests.post(GROQ_API_URL, headers=headers, json=payload)

    # Step 3️⃣: Debugging - Log Response from Groq AI
    print("Status Code:", response.status_code)
    print("Response JSON:", response.json())

    if response.status_code == 200:
        groq_response = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    else:
        groq_response = "I'm having trouble processing your request. Please try again later."

    return jsonify({"response": groq_response})


@app.route('/books', methods=['GET'])
def get_books():
    books = list(books_collection.find({}, {"_id": 1, "title": 1, "author": 1, "genre": 1, "publication_year": 1, "image": 1, "description": 1}))
    for book in books:
        book["_id"] = str(book["_id"])  # Convert ObjectId to string
    return jsonify(books), 200

@app.route('/books/search', methods=['GET'])
def search_books():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Search query is empty!"}), 400

    search_results = list(books_collection.find(
        {"$or": [
            {"title": {"$regex": query, "$options": "i"}},
            {"author": {"$regex": query, "$options": "i"}}
        ]},
        {"_id": 1, "title": 1, "author": 1, "genre": 1, "image": 1, "description": 1}
    ))

    for book in search_results:
        book["_id"] = str(book["_id"])  # Convert ObjectId to string

    return jsonify(search_results), 200

@app.route('/books/<book_id>', methods=['GET'])
def get_book_details(book_id):
    try:
        if not ObjectId.is_valid(book_id):
            return jsonify({"error": "Invalid book ID format"}), 400

        book = books_collection.find_one({"_id": ObjectId(book_id)},
                                         {"_id": 1, "title": 1, "author": 1, "genre": 1, "publication_year": 1,
                                          "description": 1, "image": 1})
        if not book:
            return jsonify({"error": "Book not found"}), 404

        book["_id"] = str(book["_id"])  # Convert ObjectId to string
        return jsonify(book)

    except InvalidId:
        return jsonify({"error": "Invalid book ID"}), 400

@app.route('/explore')
def explore():
    return render_template('explore.html')

@app.route('/book_details')
def bookd():
    return render_template('book_details.html')


if __name__ == "__main__":
    app.run(debug=True)
