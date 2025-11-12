from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.extensions import mysql
import os
from werkzeug.utils import secure_filename

# Configurações de upload
UPLOAD_FOLDER = 'app/static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx'}

chat_blueprint = Blueprint('chat', __name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ==========================================================
# 🔹 PÁGINA PRINCIPAL DO CHAT (Admin ou Usuário)
# ==========================================================
@chat_blueprint.route('/chat')
@login_required
def chat():
    """Carrega a tela do chat com as conversas relevantes."""
    with mysql.get_cursor(dictionary=True) as (_, cursor):
        role = current_user.role

        # 🔹 ADMIN vê todas as conversas
        if role == "admin":
            cursor.execute("""
                SELECT c.id, c.room, 
                       GROUP_CONCAT(u.nome SEPARATOR ', ') AS participantes
                FROM conversations c
                JOIN conversation_participants p ON c.id = p.conversation_id
                JOIN usuarios u ON p.user_id = u.id
                GROUP BY c.id, c.room
                ORDER BY c.created_at DESC
            """)
            conversas = cursor.fetchall()
            return render_template(
                "chat/chat.html",
                role=role,
                conversas=conversas,
                current_user=current_user
            )

        # 🔹 Caso contrário, usuário comum → conversa 1:1 com admin
        cursor.execute("SELECT id FROM usuarios WHERE role = 'admin' LIMIT 1")
        admin = cursor.fetchone()
        if not admin:
            return "❌ Nenhum administrador encontrado.", 500

        conversation_id, room_name = get_or_create_conversation(current_user.id, admin["id"])

        return render_template(
            "chat/chat.html",
            role=role,
            room_name=room_name,
            conversation_id=conversation_id,
            current_user=current_user
        )
# ==========================================================
# 🔹 BUSCAR MENSAGENS DE UMA CONVERSA
# ==========================================================
@chat_blueprint.route('/chat/mensagens/<int:conversation_id>')
@login_required
def get_messages(conversation_id):
    """Retorna as mensagens salvas de uma conversa específica."""
    try:
        print(f"🧠 Buscando mensagens da conversa ID: {conversation_id}")

        with mysql.get_cursor(dictionary=True) as (_, cursor):
            cursor.execute("""
                SELECT u.nome AS user, m.message, m.created_at
                FROM messages m
                JOIN usuarios u ON u.id = m.user_id
                WHERE m.conversation_id = %s
                ORDER BY m.created_at ASC
            """, (conversation_id,))
            mensagens = cursor.fetchall()

        print(f"✅ {len(mensagens)} mensagens encontradas")
        return jsonify(mensagens)

    except Exception as e:
        print(f"❌ Erro ao carregar mensagens da conversa {conversation_id}: {e}")
        return jsonify({"error": str(e)}), 500


# ==========================================================
# 🔹 UPLOAD DE ARQUIVOS
# ==========================================================
@chat_blueprint.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """Recebe e salva um arquivo enviado no chat."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        return jsonify({'filename': filename}), 201
    return jsonify({'error': 'File type not allowed'}), 400


# ==========================================================
# 🔹 FUNÇÃO AUXILIAR: CRIAR OU OBTER CONVERSA
# ==========================================================
def get_or_create_conversation(user_a_id, user_b_id):
    """Cria ou retorna uma conversa única entre dois usuários."""
    with mysql.get_cursor(dictionary=True) as (_, cursor):
        # verifica se já existe uma conversa entre esses dois usuários
        cursor.execute("""
            SELECT c.id, c.room
            FROM conversations c
            JOIN conversation_participants p1 ON p1.conversation_id = c.id
            JOIN conversation_participants p2 ON p2.conversation_id = c.id
            WHERE p1.user_id = %s AND p2.user_id = %s
            LIMIT 1
        """, (user_a_id, user_b_id))
        existing = cursor.fetchone()

        if existing:
            return existing["id"], existing["room"]

        # senão existir, cria
        room_name = f"chat_{user_a_id}_{user_b_id}"
        cursor.execute("INSERT INTO conversations (room) VALUES (%s)", (room_name,))
        conversation_id = cursor.lastrowid

        # adiciona os dois participantes
        cursor.executemany("""
            INSERT INTO conversation_participants (conversation_id, user_id)
            VALUES (%s, %s)
        """, [(conversation_id, user_a_id), (conversation_id, user_b_id)])

        return conversation_id, room_name
