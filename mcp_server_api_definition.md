# MCP Server API Definition

This document defines the API for the MCP (Market Connectivity Platform) Server.

## 1. Data Formats

All requests and responses will use the JSON data format. The `Content-Type` header for requests should be `application/json`.

## 2. Authentication

Authentication is token-based.
1. The client first calls the `/connect` endpoint with their credentials.
2. Upon successful authentication, the server returns a session token.
3. This session token must be included in the `Authorization` header for all subsequent requests (e.g., `Authorization: Bearer <session_token>`).

## 3. Endpoints

### 3.1. `/connect`

This endpoint is used to establish a connection with the server and authenticate the user.

**Request:**
```json
{
  "username": "your_username",
  "password": "your_password",
  "client_id": "your_client_id"
}
```

**Response (Success):**
```json
{
  "status": "success",
  "session_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMTIzNDU2IiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
  "message": "Authentication successful"
}
```

**Response (Error):**
```json
{
  "status": "error",
  "message": "Invalid credentials"
}
```

### 3.2. `/order`

This endpoint is used to place new trading orders. Requires a valid session token in the `Authorization` header.

**Request:**
```json
{
  "symbol": "RELIANCE-EQ",
  "exchange": "NSE",
  "quantity": 10,
  "price": 2500.00,
  "order_type": "LIMIT",
  "transaction_type": "BUY",
  "product_type": "INTRADAY"
}
```

**Response (Success):**
```json
{
  "status": "success",
  "order_id": "123456789",
  "message": "Order placed successfully"
}
```

**Response (Error):**
```json
{
  "status": "error",
  "message": "Invalid symbol"
}
```

**Response (Auth Error):**
```json
{
  "status": "error",
  "message": "Authentication failed: Invalid or missing token"
}
```

### 3.4. `/marketdata/fetch`

This endpoint is used to fetch the latest available market data for instruments the client is currently subscribed to. Requires a valid session token in the `Authorization` header.

**Request:**
(No JSON body required, authentication is via header)

**Response (Success with Data):**
```json
{
  "status": "success",
  "data": {
    "NSE_256265": { 
      "ltp": 2500.50, 
      "volume": 10000,
      "open": 2490.00,
      "high": 2510.75,
      "low": 2485.10,
      "close": 2495.00,
      "change": 0.22,
      "oi": 0
    },
    "NFO_OPTIONS_XYZ": { 
      "ltp": 150.75, 
      "volume": 5000,
      "open": 140.00,
      "high": 155.20,
      "low": 138.50,
      "close": 140.00,
      "change": 7.68,
      "oi": 200000
    }
  },
  "message": "Fetched mock data for 2 subscribed instruments."
}
```

**Response (Success with No Active Subscriptions):**
```json
{
  "status": "success",
  "data": {},
  "message": "No active market data subscriptions for this session."
}
```

**Response (Auth Error):**
```json
{
  "status": "error",
  "message": "Authentication failed: Invalid or missing token"
}
```

### 3.3. `/marketdata/subscribe`

This endpoint is used to subscribe to real-time market data for specified instruments. Requires a valid session token in the `Authorization` header.

**Request:**
```json
{
  "instruments": [
    {"exchange": "NSE", "token": "256265"}, 
    {"exchange": "BSE", "token": "500325"}  
  ],
  "subscription_type": "full" 
}
```
*Note: `token` here refers to the instrument token, not the session token. `subscription_type` can be `full` (all fields) or `quote` (LTP, bid/ask).*

**Response (Success):**
```json
{
  "status": "success",
  "subscription_id": "sub_987654321",
  "message": "Successfully subscribed to 2 instruments."
}
```

**Response (Error):**
```json
{
  "status": "error",
  "message": "Invalid instrument token: 'XYZ123'"
}
```

**Response (Auth Error):**
```json
{
  "status": "error",
  "message": "Authentication failed: Invalid or missing token"
}
```
