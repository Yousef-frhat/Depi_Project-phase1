"""
ChargeHub Backend - Mobile Recharge & Scratch Cards Platform
Main Flask application with microservices architecture.
"""

import os
import logging
import time
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------

app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "chargehub-secret-change-in-production")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = int(os.getenv("JWT_TOKEN_EXPIRES", 86400))  # 24h default

CORS(app, resources={r"/api/*": {"origins": os.getenv("CORS_ORIGINS", "*")}})
jwt = JWTManager(app)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chargehub")

# ---------------------------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    from flask import Response

    REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
    REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency', ['method', 'endpoint'])

    @app.before_request
    def before_request_metrics():
        from flask import g
        import time
        g.start_time = time.time()

    @app.after_request
    def after_request_metrics(response):
        from flask import g
        import time
        if hasattr(g, 'start_time'):
            latency = time.time() - g.start_time
            REQUEST_COUNT.labels(method=request.method, endpoint=request.path, status=response.status_code).inc()
            REQUEST_LATENCY.labels(method=request.method, endpoint=request.path).observe(latency)
        return response

    @app.route("/metrics")
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    logger.info("Prometheus metrics enabled at /metrics")
except ImportError:
    logger.warning("prometheus-client not installed; metrics disabled")

# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://chargehub:chargehub@localhost:5432/chargehub",
)


def get_db():
    """Return a new database connection."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    conn.autocommit = False
    return conn


def query_db(sql, params=None, fetchone=False, commit=False):
    """Execute a query and return results."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if commit:
                conn.commit()
                try:
                    return cur.fetchone() if fetchone else cur.fetchall()
                except psycopg2.ProgrammingError:
                    return None
            return cur.fetchone() if fetchone else cur.fetchall()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Supported Operators & Recharge Amounts
# ---------------------------------------------------------------------------

OPERATORS = [
    {"id": "vodafone", "name": "Vodafone", "prefix": ["010"]},
    {"id": "etisalat", "name": "Etisalat", "prefix": ["011"]},
    {"id": "orange", "name": "Orange", "prefix": ["012"]},
    {"id": "we", "name": "WE", "prefix": ["015"]},
]

RECHARGE_AMOUNTS = [
    {"price": 10, "credit": 7},
    {"price": 20, "credit": 14},
    {"price": 30, "credit": 21},
    {"price": 50, "credit": 35},
    {"price": 100, "credit": 70},
    {"price": 150, "credit": 105},
    {"price": 200, "credit": 140},
    {"price": 500, "credit": 350},
]

# Price mapping for cards (credit/denomination -> price user pays)
# Formula: price = credit / 0.7 (rounded)
CARD_PRICE_MAP = {
    7: 10, 14: 20, 21: 30, 35: 50,
    70: 100, 105: 150, 140: 200, 350: 500,
}

# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------


@app.errorhandler(400)
def bad_request(e):
    return jsonify({"success": False, "error": "Bad request", "message": str(e)}), 400


@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({"success": False, "error": "Internal server error"}), 500


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({"success": False, "error": "Token has expired"}), 401


@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({"success": False, "error": "Invalid token"}), 401


@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({"success": False, "error": "Authorization token required"}), 401

# ===========================================================================
# AUTH SERVICE
# ===========================================================================


@app.route("/api/auth/register", methods=["POST"])
def register():
    """Register a new user account."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    # Validation
    if not username or not email or not password:
        return jsonify({"success": False, "error": "Username, email, and password are required"}), 400

    if len(username) < 3:
        return jsonify({"success": False, "error": "Username must be at least 3 characters"}), 400

    if len(password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400

    if "@" not in email or "." not in email:
        return jsonify({"success": False, "error": "Invalid email format"}), 400

    try:
        existing = query_db(
            "SELECT id FROM users WHERE username = %s OR email = %s",
            (username, email),
            fetchone=True,
        )
        if existing:
            return jsonify({"success": False, "error": "Username or email already registered"}), 409

        password_hash = generate_password_hash(password)
        user = query_db(
            """INSERT INTO users (username, email, password_hash, balance)
               VALUES (%s, %s, %s, %s)
               RETURNING id, username, email, balance, created_at""",
            (username, email, password_hash, 0.0),
            fetchone=True,
            commit=True,
        )

        access_token = create_access_token(identity=str(user["id"]))

        logger.info(f"New user registered: {username} ({email})")
        return jsonify({
            "success": True,
            "message": "Registration successful",
            "data": {
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "balance": float(user["balance"]),
                },
                "access_token": access_token,
            },
        }), 201

    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({"success": False, "error": "Registration failed"}), 500


@app.route("/api/auth/login", methods=["POST"])
def login():
    """Authenticate user and return JWT token."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required"}), 400

    try:
        user = query_db(
            "SELECT id, username, email, password_hash, balance FROM users WHERE email = %s",
            (email,),
            fetchone=True,
        )

        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"success": False, "error": "Invalid email or password"}), 401

        access_token = create_access_token(identity=str(user["id"]))

        logger.info(f"User logged in: {user['username']}")
        return jsonify({
            "success": True,
            "message": "Login successful",
            "data": {
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "balance": float(user["balance"]),
                },
                "access_token": access_token,
            },
        }), 200

    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({"success": False, "error": "Login failed"}), 500


@app.route("/api/auth/profile", methods=["GET"])
@jwt_required()
def profile():
    """Get current user profile."""
    user_id = get_jwt_identity()
    try:
        user = query_db(
            "SELECT id, username, email, balance, created_at FROM users WHERE id = %s",
            (user_id,),
            fetchone=True,
        )
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        return jsonify({
            "success": True,
            "data": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "balance": float(user["balance"]),
                "created_at": user["created_at"].isoformat() if user["created_at"] else None,
            },
        }), 200

    except Exception as e:
        logger.error(f"Profile error: {e}")
        return jsonify({"success": False, "error": "Failed to fetch profile"}), 500

# ===========================================================================
# RECHARGE SERVICE
# ===========================================================================


@app.route("/api/recharge/operators", methods=["GET"])
def get_operators():
    """List supported mobile operators and recharge amounts."""
    return jsonify({
        "success": True,
        "data": {
            "operators": OPERATORS,
            "amounts": RECHARGE_AMOUNTS,
        },
    }), 200


@app.route("/api/recharge", methods=["POST"])
@jwt_required()
def recharge():
    """Recharge a mobile phone number."""
    user_id = get_jwt_identity()
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    phone_number = data.get("phone_number", "").strip()
    operator = data.get("operator", "").strip().lower()
    amount = data.get("amount")  # This is the credit value

    # Validation
    if not phone_number or not operator or not amount:
        return jsonify({"success": False, "error": "phone_number, operator, and amount are required"}), 400

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid amount"}), 400

    # Find matching recharge entry by credit value
    recharge_entry = None
    for entry in RECHARGE_AMOUNTS:
        if entry["credit"] == amount:
            recharge_entry = entry
            break

    if not recharge_entry:
        valid_credits = [e["credit"] for e in RECHARGE_AMOUNTS]
        return jsonify({
            "success": False,
            "error": f"Invalid credit amount. Allowed values: {valid_credits}",
        }), 400

    price = recharge_entry["price"]
    credit = recharge_entry["credit"]

    # Validate operator
    valid_operators = [op["id"] for op in OPERATORS]
    if operator not in valid_operators:
        return jsonify({"success": False, "error": f"Invalid operator. Choose from: {valid_operators}"}), 400

    # Validate phone number format (Egyptian format: 01XXXXXXXXX)
    if len(phone_number) != 11 or not phone_number.startswith("0"):
        return jsonify({"success": False, "error": "Phone number must be 11 digits starting with 0"}), 400

    # Validate phone prefix matches selected operator
    operator_prefixes = {
        "vodafone": "010",
        "etisalat": "011",
        "orange": "012",
        "we": "015",
    }
    expected_prefix = operator_prefixes.get(operator)
    if expected_prefix and not phone_number.startswith(expected_prefix):
        return jsonify({
            "success": False,
            "error": f"رقم الهاتف لا يتوافق مع الشبكة المختارة. {operator} يبدأ بـ {expected_prefix}",
        }), 400

    try:
        # Check user balance - deduct price (not credit)
        user = query_db(
            "SELECT id, balance FROM users WHERE id = %s",
            (user_id,),
            fetchone=True,
        )

        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        if float(user["balance"]) < price:
            return jsonify({"success": False, "error": "Insufficient balance"}), 400

        # Deduct price from balance and record credit in transaction
        conn = get_db()
        try:
            with conn.cursor() as cur:
                # Deduct price from balance
                cur.execute(
                    "UPDATE users SET balance = balance - %s WHERE id = %s AND balance >= %s",
                    (price, user_id, price),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    return jsonify({"success": False, "error": "Insufficient balance"}), 400

                # Record transaction with credit amount
                cur.execute(
                    """INSERT INTO transactions (user_id, type, operator, amount, phone_number, status)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       RETURNING id, type, operator, amount, phone_number, status, created_at""",
                    (user_id, "recharge", operator, credit, phone_number, "completed"),
                )
                transaction = cur.fetchone()
                conn.commit()

            logger.info(f"Recharge successful: user={user_id}, operator={operator}, credit={credit}, price={price}")
            return jsonify({
                "success": True,
                "message": f"Successfully recharged {phone_number} with {credit} EGP",
                "data": {
                    "transaction_id": transaction["id"],
                    "type": transaction["type"],
                    "operator": transaction["operator"],
                    "amount": float(transaction["amount"]),
                    "phone_number": transaction["phone_number"],
                    "status": transaction["status"],
                    "created_at": transaction["created_at"].isoformat(),
                },
            }), 200

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Recharge error: {e}")
        return jsonify({"success": False, "error": "Recharge failed"}), 500

# ===========================================================================
# CARDS SERVICE
# ===========================================================================


@app.route("/api/cards/available", methods=["GET"])
def available_cards():
    """List available scratch cards grouped by operator and denomination with price."""
    try:
        cards = query_db(
            """SELECT operator, denomination, price, COUNT(*) as available_count
               FROM cards
               WHERE is_sold = FALSE
               GROUP BY operator, denomination, price
               ORDER BY operator, denomination""",
        )

        return jsonify({
            "success": True,
            "data": [
                {
                    "operator": card["operator"],
                    "denomination": float(card["denomination"]),
                    "price": float(card["price"]) if card.get("price") else CARD_PRICE_MAP.get(int(card["denomination"]), float(card["denomination"])),
                    "available_count": card["available_count"],
                }
                for card in cards
            ],
        }), 200

    except Exception as e:
        logger.error(f"Available cards error: {e}")
        return jsonify({"success": False, "error": "Failed to fetch available cards"}), 500


@app.route("/api/cards/purchase", methods=["POST"])
@jwt_required()
def purchase_card():
    """Purchase a scratch card. Deducts price (not denomination) from balance."""
    user_id = get_jwt_identity()
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    operator = data.get("operator", "").strip().lower()
    denomination = data.get("denomination")

    if not operator or not denomination:
        return jsonify({"success": False, "error": "operator and denomination are required"}), 400

    try:
        denomination = float(denomination)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid denomination"}), 400

    # Validate operator
    valid_operators = [op["id"] for op in OPERATORS]
    if operator not in valid_operators:
        return jsonify({"success": False, "error": f"Invalid operator. Choose from: {valid_operators}"}), 400

    # Get the price for this denomination
    price = CARD_PRICE_MAP.get(int(denomination))
    if not price:
        return jsonify({"success": False, "error": "Invalid denomination"}), 400

    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                # Check user balance against price
                cur.execute("SELECT balance FROM users WHERE id = %s FOR UPDATE", (user_id,))
                user = cur.fetchone()

                if not user:
                    conn.rollback()
                    return jsonify({"success": False, "error": "User not found"}), 404

                if float(user["balance"]) < price:
                    conn.rollback()
                    return jsonify({"success": False, "error": "Insufficient balance"}), 400

                # Find available card
                cur.execute(
                    """SELECT id, serial_number, pin FROM cards
                       WHERE operator = %s AND denomination = %s AND is_sold = FALSE
                       LIMIT 1 FOR UPDATE""",
                    (operator, denomination),
                )
                card = cur.fetchone()

                if not card:
                    conn.rollback()
                    return jsonify({
                        "success": False,
                        "error": "No cards available for this operator/denomination"
                    }), 404

                # Mark card as sold
                cur.execute(
                    "UPDATE cards SET is_sold = TRUE, sold_to = %s, sold_at = NOW() WHERE id = %s",
                    (user_id, card["id"]),
                )

                # Deduct price from balance (not denomination)
                cur.execute(
                    "UPDATE users SET balance = balance - %s WHERE id = %s",
                    (price, user_id),
                )

                # Record transaction with denomination amount
                cur.execute(
                    """INSERT INTO transactions (user_id, type, operator, amount, phone_number, status)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       RETURNING id, created_at""",
                    (user_id, "card_purchase", operator, denomination, None, "completed"),
                )
                transaction = cur.fetchone()
                conn.commit()

            logger.info(f"Card purchased: user={user_id}, operator={operator}, denomination={denomination}, price={price}")
            return jsonify({
                "success": True,
                "message": "Card purchased successfully",
                "data": {
                    "transaction_id": transaction["id"],
                    "card": {
                        "serial_number": card["serial_number"],
                        "pin": card["pin"],
                        "operator": operator,
                        "denomination": denomination,
                    },
                },
            }), 200

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Card purchase error: {e}")
        return jsonify({"success": False, "error": "Card purchase failed"}), 500

# ===========================================================================
# TRANSACTIONS SERVICE
# ===========================================================================


@app.route("/api/transactions", methods=["GET"])
@jwt_required()
def transactions():
    """Get user transaction history with pagination."""
    user_id = get_jwt_identity()

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(per_page, 100)  # Cap at 100
    offset = (page - 1) * per_page

    try:
        count_result = query_db(
            "SELECT COUNT(*) as total FROM transactions WHERE user_id = %s",
            (user_id,),
            fetchone=True,
        )
        total = count_result["total"] if count_result else 0

        rows = query_db(
            """SELECT id, type, operator, amount, phone_number, status, created_at
               FROM transactions
               WHERE user_id = %s
               ORDER BY created_at DESC
               LIMIT %s OFFSET %s""",
            (user_id, per_page, offset),
        )

        return jsonify({
            "success": True,
            "data": {
                "transactions": [
                    {
                        "id": row["id"],
                        "type": row["type"],
                        "operator": row["operator"],
                        "amount": float(row["amount"]),
                        "phone_number": row["phone_number"],
                        "status": row["status"],
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    }
                    for row in rows
                ],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "pages": (total + per_page - 1) // per_page,
                },
            },
        }), 200

    except Exception as e:
        logger.error(f"Transactions error: {e}")
        return jsonify({"success": False, "error": "Failed to fetch transactions"}), 500

# ===========================================================================
# ADMIN ENDPOINTS
# ===========================================================================


@app.route("/api/admin/stats", methods=["GET"])
def admin_stats():
    """Get platform statistics for admin dashboard."""
    try:
        users_count = query_db("SELECT COUNT(*) as count FROM users", fetchone=True)
        transactions_count = query_db("SELECT COUNT(*) as count FROM transactions", fetchone=True)
        cards_sold = query_db("SELECT COUNT(*) as count FROM cards WHERE is_sold = TRUE", fetchone=True)
        cards_available = query_db("SELECT COUNT(*) as count FROM cards WHERE is_sold = FALSE", fetchone=True)
        revenue = query_db(
            "SELECT COALESCE(SUM(amount), 0) as total FROM transactions "
            "WHERE status = 'completed'",
            fetchone=True
        )

        recent_transactions = query_db(
            """SELECT t.id, t.type, t.operator, t.amount, t.phone_number, t.status, t.created_at,
                      u.username, u.id as user_id
               FROM transactions t
               JOIN users u ON t.user_id = u.id
               ORDER BY t.created_at DESC LIMIT 50"""
        )

        users = query_db(
            "SELECT id, username, email, balance, created_at FROM users ORDER BY created_at DESC"
        )

        # Cards inventory per operator
        cards_inventory = query_db(
            """SELECT operator, denomination,
                      COUNT(*) FILTER (WHERE is_sold = FALSE) as available,
                      COUNT(*) FILTER (WHERE is_sold = TRUE) as sold
               FROM cards
               GROUP BY operator, denomination
               ORDER BY operator, denomination"""
        )

        return jsonify({
            "success": True,
            "data": {
                "stats": {
                    "total_users": users_count["count"] if users_count else 0,
                    "total_transactions": transactions_count["count"] if transactions_count else 0,
                    "cards_sold": cards_sold["count"] if cards_sold else 0,
                    "cards_available": cards_available["count"] if cards_available else 0,
                    "total_revenue": float(revenue["total"]) if revenue else 0,
                },
                "recent_transactions": [
                    {
                        "id": t["id"],
                        "user_id": t["user_id"],
                        "username": t["username"],
                        "type": t["type"],
                        "operator": t["operator"],
                        "amount": float(t["amount"]),
                        "phone_number": t["phone_number"],
                        "status": t["status"],
                        "created_at": t["created_at"].isoformat() if t["created_at"] else None,
                    }
                    for t in recent_transactions
                ],
                "users": [
                    {
                        "id": u["id"],
                        "username": u["username"],
                        "email": u["email"],
                        "balance": float(u["balance"]),
                        "created_at": u["created_at"].isoformat() if u["created_at"] else None,
                    }
                    for u in users
                ],
                "cards_inventory": [
                    {
                        "operator": ci["operator"],
                        "denomination": float(ci["denomination"]),
                        "available": ci["available"],
                        "sold": ci["sold"],
                    }
                    for ci in cards_inventory
                ],
            },
        }), 200

    except Exception as e:
        logger.error(f"Admin stats error: {e}")
        return jsonify({"success": False, "error": "Failed to fetch admin stats"}), 500


@app.route("/api/admin/user/<int:uid>/transactions", methods=["GET"])
def admin_user_transactions(uid):
    """Get transaction history for a specific user (admin)."""
    try:
        rows = query_db(
            """SELECT id, type, operator, amount, phone_number, status, created_at
               FROM transactions
               WHERE user_id = %s
               ORDER BY created_at DESC
               LIMIT 100""",
            (uid,),
        )
        return jsonify({
            "success": True,
            "data": [
                {
                    "id": row["id"],
                    "type": row["type"],
                    "operator": row["operator"],
                    "amount": float(row["amount"]),
                    "phone_number": row["phone_number"],
                    "status": row["status"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }
                for row in rows
            ],
        }), 200
    except Exception as e:
        logger.error(f"Admin user transactions error: {e}")
        return jsonify({"success": False, "error": "Failed to fetch user transactions"}), 500


@app.route("/api/admin/add-balance", methods=["POST"])
def admin_add_balance():
    """Add balance to a user account (admin)."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    user_id = data.get("user_id")
    amount = data.get("amount")

    if not user_id or not amount:
        return jsonify({"success": False, "error": "user_id and amount required"}), 400

    try:
        amount = float(amount)
        if amount <= 0:
            return jsonify({"success": False, "error": "Amount must be positive"}), 400

        result = query_db(
            "UPDATE users SET balance = balance + %s WHERE id = %s RETURNING id, username, balance",
            (amount, user_id),
            fetchone=True,
            commit=True,
        )

        if not result:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Record deposit transaction
        query_db(
            """INSERT INTO transactions (user_id, type, operator, amount, status)
               VALUES (%s, 'deposit', 'admin', %s, 'completed')""",
            (user_id, amount),
            commit=True,
        )

        return jsonify({
            "success": True,
            "message": f"Added {amount} EGP to {result['username']}",
            "data": {"new_balance": float(result["balance"])},
        }), 200

    except Exception as e:
        logger.error(f"Add balance error: {e}")
        return jsonify({"success": False, "error": "Failed to add balance"}), 500

# ===========================================================================
# DEPOSIT REQUESTS (Transfer Proof Upload)
# ===========================================================================

UPLOAD_FOLDER = '/app/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/api/deposit-request", methods=["POST"])
@jwt_required()
def create_deposit_request():
    """Upload transfer proof and create a deposit request."""
    user_id = get_jwt_identity()

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "File type not allowed. Use: png, jpg, jpeg, gif, webp"}), 400

    amount = request.form.get('amount')
    credit_amount = request.form.get('credit_amount')
    payment_method = request.form.get('payment_method', '')

    if not amount or not credit_amount:
        return jsonify({"success": False, "error": "amount and credit_amount are required"}), 400

    try:
        amount = float(amount)
        credit_amount = float(credit_amount)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid amount values"}), 400

    # Save file with unique name
    timestamp = int(time.time())
    filename = f"{user_id}_{timestamp}_{secure_filename(file.filename)}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        result = query_db(
            """INSERT INTO deposit_requests (user_id, amount, credit_amount, payment_method, proof_filename)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, status, created_at""",
            (user_id, amount, credit_amount, payment_method, filename),
            fetchone=True,
            commit=True,
        )

        logger.info(f"Deposit request created: user={user_id}, amount={amount}, file={filename}")
        return jsonify({
            "success": True,
            "message": "Deposit request submitted successfully",
            "data": {
                "id": result["id"],
                "status": result["status"],
                "created_at": result["created_at"].isoformat() if result["created_at"] else None,
            },
        }), 201

    except Exception as e:
        logger.error(f"Deposit request error: {e}")
        return jsonify({"success": False, "error": "Failed to create deposit request"}), 500


@app.route("/api/admin/deposit-requests", methods=["GET"])
def admin_deposit_requests():
    """List all deposit requests with user info."""
    try:
        rows = query_db(
            """SELECT dr.id, dr.user_id, dr.amount, dr.credit_amount, dr.payment_method,
                      dr.proof_filename, dr.status, dr.created_at, dr.reviewed_at,
                      u.username, u.email
               FROM deposit_requests dr
               JOIN users u ON dr.user_id = u.id
               ORDER BY dr.created_at DESC"""
        )

        return jsonify({
            "success": True,
            "data": [
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "email": row["email"],
                    "amount": float(row["amount"]),
                    "credit_amount": float(row["credit_amount"]),
                    "payment_method": row["payment_method"],
                    "proof_filename": row["proof_filename"],
                    "status": row["status"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
                }
                for row in rows
            ],
        }), 200

    except Exception as e:
        logger.error(f"Admin deposit requests error: {e}")
        return jsonify({"success": False, "error": "Failed to fetch deposit requests"}), 500


@app.route("/api/admin/deposit-requests/<int:req_id>/approve", methods=["POST"])
def admin_approve_deposit(req_id):
    """Approve a deposit request - add credit to user balance."""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                # Get the deposit request
                cur.execute(
                    "SELECT id, user_id, credit_amount, status FROM deposit_requests WHERE id = %s",
                    (req_id,),
                )
                dep = cur.fetchone()

                if not dep:
                    conn.rollback()
                    return jsonify({"success": False, "error": "Deposit request not found"}), 404

                if dep["status"] != "pending":
                    conn.rollback()
                    return jsonify({"success": False, "error": "Request already processed"}), 400

                credit = float(dep["credit_amount"])
                uid = dep["user_id"]

                # Update status to approved
                cur.execute(
                    "UPDATE deposit_requests SET status = 'approved', reviewed_at = NOW() WHERE id = %s",
                    (req_id,),
                )

                # Add credit to user balance
                cur.execute(
                    "UPDATE users SET balance = balance + %s WHERE id = %s",
                    (credit, uid),
                )

                # Record transaction
                cur.execute(
                    """INSERT INTO transactions (user_id, type, operator, amount, status)
                       VALUES (%s, 'deposit', 'transfer', %s, 'completed')""",
                    (uid, credit),
                )

                conn.commit()

            logger.info(f"Deposit request {req_id} approved: user={uid}, credit={credit}")
            return jsonify({
                "success": True,
                "message": f"Approved - added {credit} EGP to user balance",
            }), 200

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Approve deposit error: {e}")
        return jsonify({"success": False, "error": "Failed to approve deposit request"}), 500


@app.route("/api/admin/deposit-requests/<int:req_id>/reject", methods=["POST"])
def admin_reject_deposit(req_id):
    """Reject a deposit request."""
    try:
        result = query_db(
            "SELECT id, status FROM deposit_requests WHERE id = %s",
            (req_id,),
            fetchone=True,
        )

        if not result:
            return jsonify({"success": False, "error": "Deposit request not found"}), 404

        if result["status"] != "pending":
            return jsonify({"success": False, "error": "Request already processed"}), 400

        query_db(
            "UPDATE deposit_requests SET status = 'rejected', reviewed_at = NOW() WHERE id = %s",
            (req_id,),
            commit=True,
        )

        logger.info(f"Deposit request {req_id} rejected")
        return jsonify({
            "success": True,
            "message": "Deposit request rejected",
        }), 200

    except Exception as e:
        logger.error(f"Reject deposit error: {e}")
        return jsonify({"success": False, "error": "Failed to reject deposit request"}), 500


@app.route("/api/uploads/<filename>", methods=["GET"])
def serve_upload(filename):
    """Serve uploaded proof images."""
    return send_from_directory(UPLOAD_FOLDER, filename)


# ===========================================================================
# HEALTH CHECK
# ===========================================================================


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint for load balancers and monitoring."""
    db_healthy = False
    try:
        query_db("SELECT 1", fetchone=True)
        db_healthy = True
    except Exception:
        pass

    status = "healthy" if db_healthy else "degraded"
    http_code = 200 if db_healthy else 503

    return jsonify({
        "success": True,
        "status": status,
        "service": "ChargeHub API",
        "version": "1.0.0",
        "components": {
            "database": "up" if db_healthy else "down",
            "api": "up",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), http_code


# ===========================================================================
# Entry Point
# ===========================================================================

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Starting ChargeHub API on port {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
