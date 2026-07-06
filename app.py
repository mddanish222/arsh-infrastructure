import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from supabase import create_client
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

load_dotenv()

# --- Config ---
# Configure static_folder as "frontend" so that local development can serve static files from root
app = Flask(__name__, static_folder="frontend", static_url_path="")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-in-render")

# Enable CORS for all API routes
CORS(app, resources={r"/api/*": {"origins": "*"}})

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
DATABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Token Auth helpers ---
def generate_token(username):
    serializer = URLSafeTimedSerializer(app.secret_key)
    return serializer.dumps(username, salt="admin-login-salt")

def verify_token(token):
    serializer = URLSafeTimedSerializer(app.secret_key)
    try:
        # Token expires in 24 hours (86400 seconds)
        return serializer.loads(token, salt="admin-login-salt", max_age=86400)
    except (SignatureExpired, BadSignature):
        return None

# --- DB helpers ---
def get_db():
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        return conn
    except Exception as e:
        print("DATABASE CONNECTION ERROR:", e)
        return None

def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# --- Supabase Storage upload ---
def upload_image(file):
    safe_name = datetime.now().strftime("%Y%m%d%H%M%S%f_") + secure_filename(file.filename)
    file_bytes = file.read()
    supabase.storage.from_("uploads").upload(
        safe_name,
        file_bytes,
        {"content-type": file.content_type}
    )
    public_url = supabase.storage.from_("uploads").get_public_url(safe_name)
    return public_url

# --- Auth decorator ---
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        
        token = auth_header.split(" ")[1]
        user = verify_token(token)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
            
        return view(*args, **kwargs)
    return wrapped

# --- Serves frontend static pages locally ---
@app.route("/")
def home():
    return app.send_static_file("index.html")

ADMIN_LOGIN_PATH = os.getenv("ADMIN_LOGIN_PATH", "/login").strip()
if not ADMIN_LOGIN_PATH.startswith("/"):
    ADMIN_LOGIN_PATH = "/" + ADMIN_LOGIN_PATH

@app.route(ADMIN_LOGIN_PATH)
def admin_login_page():
    return app.send_static_file("login.html")

# --- API Routes ---

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    password = data.get("password") or ""
    if password == ADMIN_PASSWORD:
        token = generate_token("admin")
        return jsonify({"success": True, "token": token})
    return jsonify({"success": False, "error": "Incorrect password"}), 401

@app.route("/api/auth-check", methods=["GET"])
@login_required
def api_auth_check():
    return jsonify({"success": True})

@app.route("/api/search", methods=["POST"])
def search_update():
    data = request.get_json() or {}
    project_name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    start_date = (data.get("start_date") or "").strip()
    end_date = (data.get("end_date") or "").strip()

    if not (project_name and phone):
        return jsonify({"error": "Project Name and Phone Number are required", "results": []}), 400

    conn = get_db()
    if conn is None:
        return jsonify({"error": "Database unavailable", "results": []}), 503

    c = get_cursor(conn)
    query = """
        SELECT id, project_name, phone, date, details, images
        FROM updates
        WHERE LOWER(project_name) = LOWER(%s) AND phone = %s
    """
    params = [project_name, phone]

    if start_date and end_date:
        query += " AND date BETWEEN %s AND %s"
        params.extend([start_date, end_date])

    query += " ORDER BY date DESC, id DESC"
    c.execute(query, tuple(params))
    results = c.fetchall()
    c.close()
    conn.close()

    # Format dates to string YYYY-MM-DD for JSON serialization
    formatted_results = []
    for r in results:
        r = dict(r)
        if hasattr(r["date"], "strftime"):
            r["date"] = r["date"].strftime("%Y-%m-%d")
        formatted_results.append(r)

    return jsonify({"results": formatted_results})

@app.route("/api/contact-submit", methods=["POST"])
def contact_submit():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    infra_type = (data.get("type") or "").strip()

    if not (name and email and infra_type):
        return jsonify({"error": "All fields are required."}), 400

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    if conn is None:
        return jsonify({"error": "Database unavailable. Please try again later."}), 503

    c = get_cursor(conn)
    c.execute(
        "INSERT INTO contact_requests (name, email, type, date) VALUES (%s, %s, %s, %s)",
        (name, email, infra_type, date_str)
    )
    conn.commit()
    c.close()
    conn.close()

    return jsonify({"success": True})

# --- Admin API Endpoints ---

@app.route("/api/admin/updates", methods=["GET", "POST"])
@login_required
def api_admin_updates():
    conn = get_db()
    if conn is None:
        return jsonify({"error": "Database unavailable."}), 503

    if request.method == "POST":
        project_name = request.form.get("project_name", "").strip()
        phone = request.form.get("phone", "").strip()
        details = request.form.get("details", "").strip()
        date_str = request.form.get("date", "").strip()

        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        if not (project_name and phone and details):
            conn.close()
            return jsonify({"error": "All fields are required."}), 400

        uploaded_files = request.files.getlist("images")
        saved_urls = []
        for f in uploaded_files:
            if f and f.filename:
                url = upload_image(f)
                saved_urls.append(url)

        images_str = ",".join(saved_urls) if saved_urls else None

        c = get_cursor(conn)
        c.execute(
            "INSERT INTO updates (project_name, phone, date, details, images) VALUES (%s, %s, %s, %s, %s)",
            (project_name, phone, date_str, details, images_str),
        )
        conn.commit()
        c.close()
        conn.close()
        return jsonify({"success": True})

    # GET request: fetch recent updates
    c = get_cursor(conn)
    c.execute("SELECT * FROM updates ORDER BY date DESC, id DESC LIMIT 20")
    recent = c.fetchall()
    c.close()
    conn.close()

    formatted_updates = []
    for r in recent:
        r = dict(r)
        if hasattr(r["date"], "strftime"):
            r["date"] = r["date"].strftime("%Y-%m-%d")
        formatted_updates.append(r)

    return jsonify({"updates": formatted_updates})

@app.route("/api/admin/updates/delete", methods=["POST"])
@login_required
def api_admin_updates_delete():
    data = request.get_json() or {}
    ids = data.get("delete_ids") or []
    if not ids:
        return jsonify({"error": "No updates selected."}), 400

    conn = get_db()
    if conn is None:
        return jsonify({"error": "Database unavailable."}), 503

    c = get_cursor(conn)
    # Fetch image paths to delete from Supabase storage
    c.execute("SELECT images FROM updates WHERE id IN %s", (tuple(ids),))
    rows = c.fetchall()

    for row in rows:
        if row["images"]:
            for url in row["images"].split(","):
                filename = url.split("/")[-1]
                try:
                    supabase.storage.from_("uploads").remove([filename])
                except Exception:
                    pass

    c.execute("DELETE FROM updates WHERE id IN %s", (tuple(ids),))
    conn.commit()
    c.close()
    conn.close()

    return jsonify({"success": True})

@app.route("/api/admin/updates/edit/<int:update_id>", methods=["GET", "POST"])
@login_required
def api_edit_update(update_id):
    conn = get_db()
    if conn is None:
        return jsonify({"error": "Database unavailable."}), 503

    c = get_cursor(conn)
    c.execute("SELECT * FROM updates WHERE id = %s", (update_id,))
    update = c.fetchone()

    if not update:
        c.close()
        conn.close()
        return jsonify({"error": "Update not found."}), 404

    if request.method == "POST":
        project_name = request.form.get("project_name", "").strip()
        phone = request.form.get("phone", "").strip()
        details = request.form.get("details", "").strip()
        date_str = request.form.get("date", "").strip()

        if not (project_name and phone and details):
            c.close()
            conn.close()
            return jsonify({"error": "All fields are required."}), 400

        uploaded_files = request.files.getlist("images")
        saved_urls = []
        for f in uploaded_files:
            if f and f.filename:
                url = upload_image(f)
                saved_urls.append(url)

        images_str = ",".join(saved_urls) if saved_urls else update["images"]

        c.execute(
            "UPDATE updates SET project_name=%s, phone=%s, date=%s, details=%s, images=%s WHERE id=%s",
            (project_name, phone, date_str, details, images_str, update_id),
        )
        conn.commit()
        c.close()
        conn.close()
        return jsonify({"success": True})

    # GET method: fetch detail
    c.close()
    conn.close()
    
    update = dict(update)
    if hasattr(update["date"], "strftime"):
        update["date"] = update["date"].strftime("%Y-%m-%d")

    return jsonify({"update": update})

@app.route("/api/admin/contact-requests", methods=["GET"])
@login_required
def api_contact_requests():
    conn = get_db()
    if conn is None:
        return jsonify({"error": "Database unavailable."}), 503

    c = get_cursor(conn)
    c.execute("SELECT * FROM contact_requests ORDER BY id DESC")
    rows = c.fetchall()
    c.close()
    conn.close()

    formatted_requests = []
    for r in rows:
        r = dict(r)
        if hasattr(r["date"], "strftime"):
            r["date"] = r["date"].strftime("%Y-%m-%d %H:%M:%S")
        formatted_requests.append(r)

    return jsonify({"requests": formatted_requests})

@app.route("/api/admin/contact-requests/delete", methods=["POST"])
@login_required
def api_contact_requests_delete():
    data = request.get_json() or {}
    ids = data.get("delete_ids") or []
    if not ids:
        return jsonify({"error": "No contact requests selected."}), 400

    conn = get_db()
    if conn is None:
        return jsonify({"error": "Database unavailable."}), 503

    c = get_cursor(conn)
    c.execute("DELETE FROM contact_requests WHERE id IN %s", (tuple(ids),))
    conn.commit()
    c.close()
    conn.close()

    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(debug=True)