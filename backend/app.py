import os
import psycopg2
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'testdb'),
    'user': os.getenv('DB_USER', 'testuser'),
    'password': os.getenv('DB_PASSWORD', 'testpass')
}

INSTANCE_ID = os.getenv('INSTANCE_ID', 'unknown')
PORT = os.getenv('PORT', '5000')

def format_datetime(dt):
    """Convert datetime to UTC ISO format string"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def get_db_connection():
    """Create and return database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def init_db():
    """Initialize database tables"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS todos (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    completed BOOLEAN DEFAULT FALSE,
                    instance_id VARCHAR(50),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            cur.close()
            conn.close()
            print("Database initialized successfully")
        except Exception as e:
            print(f"Database initialization error: {e}")

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'instance_id': INSTANCE_ID,
        'port': PORT,
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/api/info', methods=['GET'])
def info():
    """Get instance information"""
    return jsonify({
        'instance_id': INSTANCE_ID,
        'port': PORT,
        'hostname': os.getenv('HOSTNAME', 'unknown'),
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/api/todos', methods=['GET'])
def get_todos():
    """Get all todos"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute('''
            SELECT id, title, description, completed, instance_id, created_at, updated_at 
            FROM todos 
            ORDER BY created_at DESC
        ''')
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        todos = [{
            'id': row[0],
            'title': row[1],
            'description': row[2] or '',
            'completed': row[3],
            'instance_id': row[4],
            'created_at': format_datetime(row[5]),
            'updated_at': format_datetime(row[6])
        } for row in rows]
        
        return jsonify({
            'todos': todos,
            'instance_id': INSTANCE_ID,
            'count': len(todos)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/todos', methods=['POST'])
def create_todo():
    """Create new todo"""
    data = request.get_json()
    title = data.get('title', '').strip() if data else ''
    description = data.get('description', '').strip() if data else ''
    
    if not title:
        return jsonify({'error': 'Title is required'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO todos (title, description, instance_id) 
            VALUES (%s, %s, %s) 
            RETURNING id, title, description, completed, created_at, updated_at
        ''', (title, description, INSTANCE_ID))
        
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'id': row[0],
            'title': row[1],
            'description': row[2] or '',
            'completed': row[3],
            'instance_id': INSTANCE_ID,
            'created_at': format_datetime(row[4]),
            'updated_at': format_datetime(row[5])
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/todos/<int:todo_id>', methods=['PUT'])
def update_todo(todo_id):
    """Update todo"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor()
        
        cur.execute('SELECT id FROM todos WHERE id = %s', (todo_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Todo not found'}), 404
        
        updates = []
        values = []
        
        if 'title' in data:
            updates.append('title = %s')
            values.append(data['title'].strip())
        
        if 'description' in data:
            updates.append('description = %s')
            values.append(data['description'].strip())
        
        if 'completed' in data:
            updates.append('completed = %s')
            values.append(bool(data['completed']))
        
        if not updates:
            cur.close()
            conn.close()
            return jsonify({'error': 'No fields to update'}), 400
        
        updates.append('updated_at = CURRENT_TIMESTAMP')
        updates.append('instance_id = %s')
        values.append(INSTANCE_ID)
        values.append(todo_id)
        
        query = f'UPDATE todos SET {", ".join(updates)} WHERE id = %s RETURNING id, title, description, completed, instance_id, created_at, updated_at'
        
        cur.execute(query, values)
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'id': row[0],
            'title': row[1],
            'description': row[2] or '',
            'completed': row[3],
            'instance_id': row[4],
            'created_at': format_datetime(row[5]),
            'updated_at': format_datetime(row[6])
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/todos/<int:todo_id>', methods=['DELETE'])
def delete_todo(todo_id):
    """Delete todo"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor()
        
        cur.execute('SELECT id FROM todos WHERE id = %s', (todo_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Todo not found'}), 404
        
        cur.execute('DELETE FROM todos WHERE id = %s', (todo_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Todo deleted successfully', 'instance_id': INSTANCE_ID}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print(f"Starting backend instance: {INSTANCE_ID}")
    init_db()
    app.run(host='0.0.0.0', port=int(PORT), debug=False)

