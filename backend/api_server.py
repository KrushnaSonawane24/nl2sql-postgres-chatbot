"""
Flask API Backend for React Frontend
Organized in backend/ folder for cleaner structure
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import os
from dotenv import load_dotenv

# Add src to path (use root src folder)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # Go up to project root
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from nl2sql.agent import answer_question
from nl2sql.config import load_settings
from nl2sql.db import PostgresDB, DatabaseError
from nl2sql.llm_client import LLMError

load_dotenv()

app = Flask(__name__)
CORS(app)

settings = load_settings()


@app.route('/api/query', methods=['POST'])
def query():
    """NL2SQL endpoint"""
    try:
        data = request.json
        question = data.get('question', '')
        chat_history = data.get('chat_history', [])
        
        if not question:
            return jsonify({'error': 'Question is required'}), 400
        
        db = PostgresDB(settings.database_url)
        
        response = answer_question(
            provider=settings.provider,
            api_key=settings.api_key,
            model=settings.model,
            db=db,
            question=question,
            chat_history=chat_history,
            statement_timeout_ms=settings.statement_timeout_ms,
            max_rows=settings.max_rows,
            sql_mode="write_full",
            execute=True,
            memory_user_turns=settings.memory_user_turns,
            max_sql_statements=settings.max_sql_statements
        )
        
        # Format results
        results_data = None
        if response.results:
            results_data = [r.rows for r in response.results]
            if len(results_data) == 1:
                results_data = results_data[0]
        
        return jsonify({
            'answer': response.answer,
            'sql': response.sql,
            'results': results_data,
            'kind': response.kind
        })
        
    except (LLMError, DatabaseError) as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


# Alias for langchain endpoint (same implementation for now)
@app.route('/api/langchain/query', methods=['POST'])
def query_langchain():
    """LangChain endpoint (uses same backend for now)"""
    return query()


@app.route('/api/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'provider': settings.provider,
        'model': settings.model
    })


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 NL2SQL API Backend Started!")
    print("=" * 60)
    print(f"📍 Running on: http://localhost:5000")
    print(f"🤖 Provider: {settings.provider}")
    print(f"📦 Model: {settings.model}")
    print("\n✅ Available Endpoints:")
    print("  POST /api/query              - Original NL2SQL")
    print("  POST /api/langchain/query    - LangChain NL2SQL")
    print("  GET  /api/health             - Health check")
    print("\n🌐 Frontend:")
    print("  React: Open ../frontend/index.html in browser")
    print("  Streamlit Original: streamlit run ../app.py")
    print("  Streamlit LangChain: streamlit run ../app_langchain.py")
    print("=" * 60)
    app.run(debug=True, port=5000, use_reloader=False)
