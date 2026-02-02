# Backend API - NL2SQL PostgreSQL Query Assistant

## 📁 Structure

```
backend/
├── api_server.py          ← Flask REST API
├── .env                   ← Environment variables
└── README.md             ← This file

../src/                    ← Shared Python code (in project root)
├── nl2sql/               ← Core NL2SQL logic
└── nl2sql_langchain/     ← LangChain integration
```

---

## 🚀 How to Run Backend

### **Start API Server:**
```bash
cd backend
python api_server.py
```

Backend will start on: `http://localhost:5000`

---

## 📡 API Endpoints

### **1. Query Endpoint**
```http
POST http://localhost:5000/api/query
Content-Type: application/json

{
  "question": "Show top 10 users",
  "chat_history": []
}
```

**Response:**
```json
{
  "answer": "Query returned 10 row(s).",
  "sql": "SELECT * FROM users LIMIT 10;",
  "results": [...],
  "kind": "sql"
}
```

### **2. LangChain Query Endpoint**
```http
POST http://localhost:5000/api/langchain/query
Content-Type: application/json

{
  "question": "Show top 10 users"
}
```

### **3. Health Check**
```http
GET http://localhost:5000/api/health
```

---

## ⚙️ Environment Variables

Create/edit `.env` file:

```env
# Database
DATABASE_URL=postgresql://user:pass@host:port/dbname

# LLM Provider (gemini or groq)
PROVIDER=gemini
GEMINI_API_KEY=your_key_here
# OR
GROQ_API_KEY=your_key_here

# Model
MODEL=gemini-1.5-flash
# OR
# MODEL=llama-3.3-70b-versatile

# Optional settings
MAX_SQL_STATEMENTS=4
STATEMENT_TIMEOUT_MS=8000
MAX_ROWS=200
MEMORY_USER_TURNS=10
```

---

## 🔗 Frontend Integration

The backend is designed to work with:

1. **React Frontend** (`../frontend/`)
2. **Streamlit Original** (`../app.py`)
3. **Streamlit LangChain** (`../app_langchain.py`)

---

## 🐛 Troubleshooting

### **Issue: Module not found**
Solution: Make sure you're running from the `backend/` directory:
```bash
cd backend
python api_server.py
```

### **Issue: Database connection error**
Solution: Check your `DATABASE_URL` in `.env`

### **Issue: LLM API error**
Solution: Verify your API key is correct in `.env`

---

## 📦 Dependencies

```bash
pip install flask flask-cors python-dotenv
pip install langchain langchain-google-genai langchain-groq
pip install psycopg2-binary sqlparse
```

---

**Status:** ✅ Backend organized and ready for production!
