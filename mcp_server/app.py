from flask import Flask, request, jsonify
import uuid
import functools # For token_required decorator
import random # For mock data updates

app = Flask(__name__)

# --- Basic Risk Parameters ---
MAX_ORDER_QUANTITY = 100000  # Max quantity for a single order
MAX_ORDER_VALUE = 5000000   # Max value (qty * price) for a single order (for LIMIT/SL)
# TODO: Consider MAX_ORDERS_PER_MINUTE_PER_USER, MAX_OPEN_ORDERS_PER_USER, etc. for future.

# --- Order Status Definitions ---
ORDER_STATUSES = {
    "PENDING_SEND": "PENDING_SEND",
    "SENT_TO_BROKER": "SENT_TO_BROKER",
    "OPEN": "OPEN",
    "PARTIALLY_FILLED": "PARTIALLY_FILLED",
    "FILLED": "FILLED",
    "CANCELLED": "CANCELLED",
    "REJECTED_MCP": "REJECTED_MCP",
    "REJECTED_BROKER": "REJECTED_BROKER",
    "ERROR": "ERROR"
}

# --- Allowed Order Parameter Values ---
ALLOWED_EXCHANGES = {"NSE", "NFO", "CDS", "BSE", "MCX"}
ALLOWED_ORDER_TYPES = {"MARKET", "LIMIT", "SL", "SL-M"}
ALLOWED_TRANSACTION_TYPES = {"BUY", "SELL"}
ALLOWED_PRODUCT_TYPES = {"CNC", "INTRADAY", "NORMAL", "MTF"}

# --- In-memory Stores ---
active_sessions = {}
mock_market_data_store = {}
client_subscriptions = {}


# --- Placeholder Shoonya API Functions ---

def shoonya_login(username, password, client_id):
    print(f"Attempting Shoonya login for user: {username}, client_id: {client_id}")
    if password == "fail_shoonya_login":
        return {"status": "error", "message": "Shoonya login failed (mock)"}
    return {"status": "success", "shoonya_session_id": f"mock_shoonya_session_{uuid.uuid4()}"}

def shoonya_place_order(shoonya_session_id, order_details):
    print(f"Placing Shoonya order: {order_details} with session: {shoonya_session_id}")
    if order_details.get("symbol") == "FAIL_ORDER":
        return {
            "status": "error", 
            "message": "Shoonya order placement failed (mock): Invalid symbol",
            "order_status": ORDER_STATUSES["REJECTED_BROKER"]
        }
    return {
        "status": "success", 
        "shoonya_order_id": f"mock_shoonya_order_{uuid.uuid4()}",
        "order_status": ORDER_STATUSES["SENT_TO_BROKER"] 
    }

def shoonya_subscribe_market_data(shoonya_session_id, instruments_to_subscribe):
    print(f"Subscribing to Shoonya market data for: {instruments_to_subscribe} with session: {shoonya_session_id}")
    if not instruments_to_subscribe:
        return {"status": "error", "message": "Shoonya market data subscription failed (mock): No instruments provided"}

    subscribed_keys = []
    for inst in instruments_to_subscribe:
        instrument_key = f"{inst['exchange']}_{inst['token']}" 
        subscribed_keys.append(instrument_key)
        if instrument_key not in mock_market_data_store:
            mock_market_data_store[instrument_key] = {
                "ltp": round(random.uniform(100, 3000), 2), "volume": random.randint(1000, 50000),
                "open": round(random.uniform(100, 3000), 2), "high": round(random.uniform(100, 3000), 2),
                "low": round(random.uniform(100, 3000), 2), "close": round(random.uniform(100, 3000), 2),
                "change": round(random.uniform(-5, 5), 2),
                "oi": random.randint(100, 100000) if inst['exchange'] in {"NFO", "MCX"} else 0
            }
            mock_market_data_store[instrument_key]['high'] = max(mock_market_data_store[instrument_key]['high'], mock_market_data_store[instrument_key]['ltp'], mock_market_data_store[instrument_key]['open'])
            mock_market_data_store[instrument_key]['low'] = min(mock_market_data_store[instrument_key]['low'], mock_market_data_store[instrument_key]['ltp'], mock_market_data_store[instrument_key]['open'])
    return {"status": "success", "shoonya_subscription_id": f"mock_shoonya_sub_{uuid.uuid4()}", "subscribed_keys": subscribed_keys}

# --- Authentication Decorator ---

def token_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try: token = auth_header.split(None, 1)[1]
            except IndexError: token = None
        if not token: return jsonify({"status": "error", "message": "Authentication token is missing or invalid format!"}), 401
        if token not in active_sessions: return jsonify({"status": "error", "message": "Invalid or expired MCP session token!"}), 401
        
        kwargs['current_session_token'] = token
        kwargs['current_user_session'] = active_sessions[token]
        return f(*args, **kwargs)
    return decorated_function

# --- API Endpoints ---

@app.route('/connect', methods=['POST'])
def connect():
    data = request.get_json()
    if not data: return jsonify({"status": "error", "message": "Request body must be JSON"}), 400
    username, password, client_id = data.get('username'), data.get('password'), data.get('client_id')
    if not all([username, password, client_id]): return jsonify({"status": "error", "message": "Missing credentials."}), 400
    
    shoonya_auth_result = shoonya_login(username, password, client_id)
    if shoonya_auth_result["status"] == "error": 
        return jsonify({"status": "error", "message": f"Shoonya auth failed: {shoonya_auth_result.get('message')}"}), 401

    mcp_session_token = str(uuid.uuid4())
    active_sessions[mcp_session_token] = {"username": username, "client_id": client_id, "shoonya_session_id": shoonya_auth_result["shoonya_session_id"]}
    return jsonify({"status": "success", "session_token": mcp_session_token, "message": "Auth successful."}), 200

@app.route('/order', methods=['POST'])
@token_required
def place_order(current_user_session, current_session_token):
    data = request.get_json()
    if not data: return jsonify({"status": "error", "message": "Request body must be JSON", "order_status": ORDER_STATUSES["REJECTED_MCP"]}), 400

    # --- MCP-Level Order Validation (including Risk) ---
    required_fields = ["symbol", "exchange", "quantity", "order_type", "transaction_type", "product_type"]
    errors = []
    
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields: errors.append(f"Missing order parameters: {', '.join(missing_fields)}")

    # Basic field presence check before accessing them for detailed validation
    if errors: # If basic fields are missing, return early
        return jsonify({"status": "error", "message": "; ".join(errors), "order_status": ORDER_STATUSES["REJECTED_MCP"]}), 400

    # Detailed Validations
    if data.get("exchange") not in ALLOWED_EXCHANGES: errors.append(f"Invalid exchange. Allowed: {ALLOWED_EXCHANGES}")
    if data.get("order_type") not in ALLOWED_ORDER_TYPES: errors.append(f"Invalid order_type. Allowed: {ALLOWED_ORDER_TYPES}")
    if data.get("transaction_type") not in ALLOWED_TRANSACTION_TYPES: errors.append(f"Invalid transaction_type. Allowed: {ALLOWED_TRANSACTION_TYPES}")
    if data.get("product_type") not in ALLOWED_PRODUCT_TYPES: errors.append(f"Invalid product_type. Allowed: {ALLOWED_PRODUCT_TYPES}")
    
    quantity = data.get("quantity")
    if not isinstance(quantity, int) or quantity <= 0: 
        errors.append("Quantity must be a positive integer.")
    else: # Quantity is valid, proceed to risk checks involving quantity
        if quantity > MAX_ORDER_QUANTITY:
            errors.append(f"Order quantity {quantity} exceeds maximum allowed {MAX_ORDER_QUANTITY}.")

    price = data.get("price") # Price may be None or 0 for MARKET orders
    order_type = data.get("order_type")
    if order_type in {"LIMIT", "SL"}:
        if not isinstance(price, (int, float)) or price <= 0:
            errors.append(f"Price must be a positive number for {order_type} orders.")
        elif quantity and isinstance(quantity, int) and quantity > 0 : # If price and quantity are valid, check order value
            order_value = quantity * price
            if order_value > MAX_ORDER_VALUE:
                errors.append(f"Order value {order_value} (qty {quantity} * price {price}) exceeds maximum allowed {MAX_ORDER_VALUE}.")
    # Note: MAX_ORDER_VALUE check is currently only for LIMIT/SL orders as per subtask instructions.

    if errors:
        return jsonify({"status": "error", "message": "; ".join(errors), "order_status": ORDER_STATUSES["REJECTED_MCP"]}), 400
    # --- End MCP-Level Order Validation ---

    shoonya_session_id = current_user_session["shoonya_session_id"]
    shoonya_order_result = shoonya_place_order(shoonya_session_id, data)
    
    response_payload = {
        "status": shoonya_order_result["status"],
        "message": shoonya_order_result.get("message", "Order processing complete."),
        "order_status": shoonya_order_result.get("order_status", ORDER_STATUSES["ERROR"])
    }
    if shoonya_order_result["status"] == "success":
        response_payload["order_id"] = shoonya_order_result.get("shoonya_order_id")
    
    return jsonify(response_payload), 200 if shoonya_order_result["status"] == "success" else 400

@app.route('/marketdata/subscribe', methods=['POST'])
@token_required
def subscribe_market_data(current_user_session, current_session_token):
    data = request.get_json()
    if not data: return jsonify({"status": "error", "message": "Request body must be JSON"}), 400
    instruments = data.get('instruments')
    if not instruments or not isinstance(instruments, list): return jsonify({"status": "error", "message": "Invalid 'instruments' list."}), 400
    
    valid_instruments = []
    for inst in instruments:
        if not (isinstance(inst, dict) and all(k in inst for k in ("exchange", "token"))):
            return jsonify({"status": "error", "message": "Invalid instrument format."}), 400
        valid_instruments.append(inst)
    if not valid_instruments: return jsonify({"status": "error", "message": "No valid instruments."}), 400

    shoonya_result = shoonya_subscribe_market_data(current_user_session["shoonya_session_id"], valid_instruments)
    if shoonya_result["status"] == "success":
        client_subscriptions.setdefault(current_session_token, [])
        newly_tracked = sum(1 for key in shoonya_result.get("subscribed_keys", []) if key not in client_subscriptions[current_session_token])
        client_subscriptions[current_session_token].extend(key for key in shoonya_result.get("subscribed_keys", []) if key not in client_subscriptions[current_session_token])
        return jsonify({"status": "success", "subscription_id": shoonya_result["shoonya_subscription_id"], "message": f"Subscribed. Tracking {newly_tracked} new. Total: {len(client_subscriptions[current_session_token])}."}), 200
    return jsonify({"status": "error", "message": shoonya_result.get("message", "Failed Shoonya subscribe.")}), 400

@app.route('/marketdata/fetch', methods=['GET'])
@token_required
def fetch_market_data(current_user_session, current_session_token):
    for key in mock_market_data_store: # Simulate data changes
        if random.random() < 0.3:
            change = random.uniform(-0.02, 0.02)
            mock_market_data_store[key]["ltp"] = round(mock_market_data_store[key]["ltp"] * (1 + change), 2)
            mock_market_data_store[key]["volume"] += random.randint(0,100)
            mock_market_data_store[key]['high'] = max(mock_market_data_store[key]['high'], mock_market_data_store[key]['ltp'])
            mock_market_data_store[key]['low'] = min(mock_market_data_store[key]['low'], mock_market_data_store[key]['ltp'])
            mock_market_data_store[key]['change'] = round(((mock_market_data_store[key]['ltp'] / mock_market_data_store[key]['open']) - 1) * 100, 2) if mock_market_data_store[key]['open'] != 0 else 0
            
    subscribed_keys = client_subscriptions.get(current_session_token, [])
    if not subscribed_keys: return jsonify({"status": "success", "data": {}, "message": "No active subscriptions."}), 200
    
    data_to_return = {key: mock_market_data_store[key] for key in subscribed_keys if key in mock_market_data_store}
    return jsonify({"status": "success", "data": data_to_return, "message": f"Fetched data for {len(data_to_return)} instruments."}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
