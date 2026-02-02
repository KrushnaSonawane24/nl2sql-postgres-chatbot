# NL2SQL PostgreSQL Chatbot

Professional Natural Language to SQL query assistant with multiple frontend options and pure black theme UI.

**Author:** Krushna Sonawane  
**GitHub:** [nl2sql-postgres-chatbot](https://github.com/KrushnaSonawane24/nl2sql-postgres-chatbot)

---

## 📁 Project Structure

```
cursor_sql_chatbot/
├── frontend/              ← React UI (ChatGPT-style)
│   ├── index.html
│   ├── styles.css        
│   ├── app.js
│   └── README.md
│
├── backend/               ← Flask REST API
│   ├── api_server.py     
│   ├── .env
│   └── README.md
│
├── src/                   ← Core Python Logic
│   ├── nl2sql/           (SQL generation, DB, LLM)
│   └── nl2sql_langchain/ (LangChain integration)
│
├── app.py                 ← Streamlit Original
├── app_langchain.py       ← Streamlit + LangChain
├── setup_database.py      ← PostgreSQL demo DB setup
│
├── .env                   ← Environment config
├── requirements.txt       ← Dependencies
└── README.md             ← This file
```

---

## 🚀 Quick Start

### **Option 1: React Frontend (Recommended)**

```bash
# 1. Start backend API
cd backend
python api_server.py

# 2. Open frontend (from project root)
start frontend\index.html
```

### **Option 2: Streamlit UI**

```bash
# Original version
streamlit run app.py

# LangChain version (with memory)
streamlit run app_langchain.py
```

---

## ⚙️ Setup

### **1. Install Dependencies**

```bash
pip install -r requirements.txt
```

Main packages:
- `streamlit` - Web UI framework
- `flask`, `flask-cors` - REST API
- `langchain`, `langchain-google-genai`, `langchain-groq` - LLM
- `psycopg2-binary` - PostgreSQL driver
- `python-dotenv` - Environment management

### **2. Configure Environment**

Create `.env` file:

```env
# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname

# LLM Provider (choose one)
PROVIDER=gemini
GEMINI_API_KEY=your_gemini_key_here

# OR
PROVIDER=groq
GROQ_API_KEY=your_groq_key_here

# Model
MODEL=gemini-1.5-flash
# OR
# MODEL=llama-3.3-70b-versatile

# Optional Settings
MAX_SQL_STATEMENTS=4
STATEMENT_TIMEOUT_MS=8000
MAX_ROWS=200
MEMORY_USER_TURNS=10
```

### **3. Setup Demo Database (Optional)**

```bash
# Edit setup_database.py with your PostgreSQL password
python setup_database.py
```

This creates:
- Database: `nl2sql_demo`
- Tables: `customers` (200 records), `orders` (200 records)
- Realistic sample data for testing

See `DATABASE_SETUP.md` for details.

---

## 🎨 UI Features

All versions feature **pure black theme**:

### **Color Palette:**
- Background: `#030303` (pure black)
- Sidebar: `#202123` (dark)
- Input: `#161618` (dark gray)
- Accent: `#10a37f` (green)
- Text: `#ececf1` (light)

### **Features:**
✅ ChatGPT-inspired dark UI  
✅ SQL code syntax highlighting  
✅ Results tables  
✅ Chat history  
✅ Professional typography  
✅ Responsive design  

---

## 🔧 Architecture

### **Frontend Options:**

1. **React** (`frontend/`)
   - Pure HTML/CSS/JS (no build needed)
   - Connects to Flask API
   - ChatGPT-style interface

2. **Streamlit Original** (`app.py`)
   - Custom NL2SQL implementation
   - Built-in chat memory

3. **Streamlit LangChain** (`app_langchain.py`)
   - LangChain for memory management
   - Advanced conversation handling

### **Backend:**

- **Flask API** (`backend/api_server.py`)
  - RESTful endpoints
  - CORS enabled
  - `/api/query` - Original version
  - `/api/langchain/query` - LangChain version
  - `/api/health` - Health check

- **Core Logic** (`src/nl2sql/`)
  - SQL generation & validation
  - Database interaction
  - LLM client (Gemini/Groq)
  - Safety checks

---

## 🎯 Features

### **Capabilities:**
- Natural language → PostgreSQL query
- Multi-language: English, Hindi, Hinglish
- SQL safety validation
- Query execution with results
- Chat memory/history
- Professional error handling

### **SQL Modes:**
- `read_only` - SELECT only
- `write_no_delete` - INSERT, UPDATE
- `write_full` - Full CRUD

### **Supported Operations:**
- SELECT with JOINs, CTEs, aggregations
- INSERT with RETURNING
- UPDATE with WHERE
- DELETE with WHERE
- CREATE TABLE/VIEW/INDEX
- Schema introspection

---

## 💡 Example Queries

### **Simple:**
```
"Show me all customers"
"Count total orders"
"What's the total sales?"
```

### **Filtering:**
```
"Show married male customers"
"Find orders above 1000"
"Orders from last month"
```

### **Aggregations:**
```
"Average order value"
"Top 10 customers by revenue"
"Count customers by marital status"
```

### **Joins:**
```
"Show customer names with their orders"
"Which customer has the most orders?"
"Products ordered by customer John"
```

### **Complex:**
```
"Customers who never ordered"
"Monthly sales trend"
"Average order value by gender"
```

---

## 📡 API Documentation

### **Endpoints:**

**POST** `/api/query`
```json
Request:
{
  "question": "Show top 10 users",
  "chat_history": []
}

Response:
{
  "answer": "Query returned 10 row(s).",
  "sql": "SELECT * FROM users LIMIT 10;",
  "results": [...],
  "kind": "sql"
}
```

**POST** `/api/langchain/query`
```json
Request:
{
  "question": "Show top 10 users"
}
```

**GET** `/api/health`
```json
Response:
{
  "status": "healthy",
  "provider": "gemini",
  "model": "gemini-1.5-flash"
}
```

See `backend/README.md` for detailed API docs.

---

## 🔒 Security

- SQL injection prevention
- Parameterized queries
- SQL safety validation
- WHERE clause enforcement (UPDATE/DELETE)
- Statement timeout limits
- Row count limits
- Read-only mode option

---

## 📚 Documentation

- **Frontend:** `frontend/README.md`
- **Backend API:** `backend/README.md`
- **Database Setup:** `DATABASE_SETUP.md`
- **UI Changes:** `UI_CHANGES.md`
- **Backend Changes:** `BACKEND_CHANGES.md`

---

## 🐛 Troubleshooting

### **Backend won't start:**
```bash
cd backend
python api_server.py
```

### **Database connection error:**
- Check PostgreSQL is running
- Verify `DATABASE_URL` in `.env`
- Test connection: `psql -h host -U user -d dbname`

### **LLM API error:**
- Verify API key in `.env`
- Check provider is correct (gemini/groq)
- Ensure model name is valid

### **Frontend shows errors:**
- Backend should be running on `http://localhost:5000`
- Check browser console (F12) for errors
- Verify CORS is enabled

---

## 🎓 Interview Talking Points

### **Technical Highlights:**

> "This is a production-ready NL2SQL assistant with:
> - Professional dark UI optimized for technical users
> - Multiple frontend options (React, Streamlit)
> - RESTful API backend for integration
> - Enterprise SQL safety validation
> - Complex PostgreSQL query support
> - LangChain for conversation memory
> - Modular, maintainable architecture"

### **Key Features:**
- Prompt engineering for SQL generation
- Schema injection for context
- Multi-turn conversation handling
- Type casting (text → numeric)
- Error recovery with clarifications
- Real-world safety constraints

---

## 🚢 Deployment

### **Local:**
```bash
# Backend
cd backend && python api_server.py

# Frontend
streamlit run app.py
# OR
start frontend\index.html
```

### **Production:**
- Backend: Railway, Render, Fly.io
- React Frontend: Vercel, Netlify
- Streamlit: Streamlit Cloud

---

## 📝 Version History

- **v3.0** - Cleaned file structure, demo database
- **v2.1** - Pure black theme (#030303)
- **v2.0** - Backend organized, single src/
- **v1.5** - React frontend added
- **v1.0** - Initial Streamlit implementation

---

## 📄 License

MIT License - Free for commercial and personal use

---

## 🙏 Acknowledgments

- Streamlit for rapid prototyping
- LangChain for LLM orchestration
- Google Gemini & Groq for LLM APIs
- PostgreSQL for robust database

---

**Status:** ✅ Production-ready with clean structure!

For questions or issues, see documentation in respective folders.
