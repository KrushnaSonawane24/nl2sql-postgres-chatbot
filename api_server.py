"""
Flask API Backend for React Frontend
Provides REST API endpoints for both original and LangChain NL2SQL implementations
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import os
from dotenv import load_dotenv

# Add src to path
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from nl2sql.agent import answer_question as answer_question_original
from nl2sql.config import load_settings
from nl2sql.db import PostgresDB, DatabaseError
from nl2sql.llm_client import LLMError

# Try importing LangChain (optional)
try:
    from nl2sql_langchain.agent_lc import LangChainAgent, NL2SQLError as LangChainError
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    LangChainAgent = None
    LangChainError = Exception

load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for React frontend

settings = load_settings()

# LangChain agent will be initialized on first request
_langchain_agent_cache = None


def get_langchain_agent():
    """Lazy initialize LangChain agent"""
    global _langchain_agent_cache
    if _langchain_agent_cache is None:
        _langchain_agent_cache = LangChainAgent(
            provider=settings.provider,
            api_key=settings.api_key,
            model=settings.model,
            sql_mode="write_full",
            max_sql_statements=settings.max_sql_statements
        )
    return _langchain_agent_cache



@app.route('/api/query', methods=['POST'])
def query_original():
    """Original NL2SQL endpoint"""
    try:
        data = request.json
        question = data.get('question', '')
        chat_history = data.get('chat_history', [])
        
        if not question:
            return jsonify({'error': 'Question is required'}), 400
        
        db = PostgresDB(settings.database_url)
        
        response = answer_question_original(
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
            # Flatten if single result
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


@app.route('/api/langchain/query', methods=['POST'])
def query_langchain():
    """LangChain NL2SQL endpoint"""
    try:
        agent = get_langchain_agent()
        
        data = request.json
        question = data.get('question', '')
        
        if not question:
            return jsonify({'error': 'Question is required'}), 400
        
        db = PostgresDB(settings.database_url)
        
        # Add to memory
        agent.add_to_memory("user", question)
        
        response = agent.answer_question(
            db=db,
            question=question,
            execute=True,
            statement_timeout_ms=settings.statement_timeout_ms,
            max_rows=settings.max_rows
        )
        
        # Add response to memory
        agent.add_to_memory("assistant", response.answer)
        
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
        
    except (DatabaseError, Exception) as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'provider': settings.provider,
        'model': settings.model,
        'langchain_enabled': True
    })


if __name__ == '__main__':
    print("Starting NL2SQL API Backend...")
    print(f"Provider: {settings.provider}")
    print(f"Model: {settings.model}")
    print(f"LangChain: {'Enabled' if langchain_agent else 'Disabled'}")
    print("\nAPI Endpoints:")
    print("  POST /api/query - Original NL2SQL")
    print("  POST /api/langchain/query - LangChain NL2SQL")
    print("  GET  /api/health - Health check")
    print("\nFrontend: Open frontend/index.html in browser")
    app.run(debug=True, port=5000)
