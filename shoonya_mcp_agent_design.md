# Shoonya MCP Agent - Design Document

## 1. Overview

*   **Purpose:** To enable an MCP (Model Context Protocol) client, such as a Large Language Model (LLM), to interact with the Shoonya Trading API. This agent will act as a bridge, translating MCP tool calls into Shoonya API requests and Shoonya responses/data into MCP-compatible formats.
*   **Core Technology:**
    *   Python
    *   MCP SDK (Python version)
    *   ShoonyaApi-py library (the official Python client for Shoonya API)

## 2. Server Structure

*   The agent will be implemented as an MCP server using the Python MCP SDK.
*   It will likely inherit from a base server class provided by the SDK (e.g., `MCPBaseServer` or similar).
*   The server will initialize an instance of the `ShoonyaApiPy` client upon startup or on the first relevant tool call. This client instance will be used for all subsequent interactions with the Shoonya API.
*   The server will manage the Shoonya API session (e.g., `susertoken`).

## 3. Authentication Strategy

### 3.1. MCP Server to Shoonya API

*   **Credential Storage:** Shoonya API credentials (user ID, password, 2FA, vendor code, API secret, IMEI) will be provided to the MCP server. The primary recommended method is through environment variables for security (e.g., `SHOONYA_USER_ID`, `SHOONYA_PASSWORD`, etc.). A configuration file (e.g., `config.ini` or `config.yaml`) read at startup could be a secondary option, but environment variables are preferred for sensitive data.
*   **Login Process:** The MCP server, using the `connect_shoonya_broker` tool (or an internal equivalent triggered by it), will perform a login to the Shoonya API using the provided credentials.
*   **Session Management:** The `susertoken` (session token) and other relevant user information (like `uid`) received from Shoonya upon successful login will be stored securely within the server's memory (associated with the MCP client session or globally if the server is single-user focused). This token will be used for all authenticated Shoonya API calls. The server will also need to handle token expiry and re-login if necessary, though Shoonya tokens are typically long-lived for the day.

### 3.2. MCP Client to MCP Server

*   **Initial Simplicity:** For the initial version, especially if the MCP server is run locally or in a trusted private network environment alongside the LLM client, direct client-to-MCP-server authentication might be minimal or omitted. The focus is on robustly authenticating the MCP server with the Shoonya API.
*   **Future Enhancement:** If deployed in a less trusted environment, standard MCP authentication mechanisms (e.g., API keys, OAuth tokens managed by the MCP SDK) could be implemented for the client-to-server connection. This is outside the scope of the initial Shoonya integration.

## 4. Proposed MCP Tools

All tools will return a standard success or error JSON structure.
*   **Success:** `{"status": "success", ...specific_tool_data...}`
*   **Error:** `{"status": "error", "message": "Error description details"}`

### 4.1. Mandatory Initial Tool

*   **Tool Name:** `connect_shoonya_broker`
    *   **Description:** Logs the MCP server into the Shoonya broker using the provided user credentials. This establishes the session with Shoonya for subsequent API calls.
    *   **Input Parameters:**
        *   `user_id: str` (Shoonya User ID)
        *   `password: str` (Shoonya Password)
        *   `two_fa_token: str` (TOTP or similar second-factor authentication token)
        *   `vendor_code: str` (Shoonya Vendor Code)
        *   `api_secret: str` (Shoonya API Key / Secret)
        *   `imei: str` (Registered IMEI for the API)
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "message": "Successfully connected to Shoonya broker.",
          "user_id": "USER_XYZ" 
        }
        ```
    *   **Output Schema (Error):**
        ```json
        {
          "status": "error",
          "message": "Shoonya login failed: [Specific error from Shoonya API]"
        }
        ```

### 4.2. Order Management Tools

(Parameters should align with `ShoonyaApiPy` methods like `place_order`, `modify_order`, `cancel_order`)

*   **Tool Name:** `place_order`
    *   **Description:** Places a trading order.
    *   **Input Parameters:**
        *   `exchange: str` (e.g., "NSE", "NFO")
        *   `tradingsymbol: str` (e.g., "SBIN-EQ", "NIFTY23JUL20000CE")
        *   `quantity: int`
        *   `price: float` (0 for MARKET orders)
        *   `order_type: str` (e.g., "LIMIT", "MARKET", "SL", "SL-M") - maps to Shoonya's `prctyp`
        *   `transaction_type: str` (e.g., "BUY", "SELL") - maps to Shoonya's `trantype`
        *   `product_type: str` (e.g., "INTRADAY", "CNC", "NORMAL", "MTF") - maps to Shoonya's `prd`
        *   `retention: str` (e.g., "DAY", "IOC") - maps to Shoonya's `ret`
        *   `remarks: str` (Optional, e.g., "algo_order_123")
        *   `price_trigger: float` (Optional, for SL/SL-M orders) - maps to Shoonya's `trigPrice`
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "order_id": "SHOONYA_ORDER_ID_123",
          "message": "Order placed successfully."
        }
        ```
    *   **Output Schema (Error):** (Includes Shoonya error details)

*   **Tool Name:** `modify_order`
    *   **Description:** Modifies an existing pending order.
    *   **Input Parameters:**
        *   `order_id: str` (The `norenordno` from Shoonya)
        *   `exchange: str`
        *   `tradingsymbol: str`
        *   `quantity: int` (Optional, new quantity)
        *   `price: float` (Optional, new price, 0 for MARKET)
        *   `order_type: str` (Optional, new order type, e.g. "LIMIT")
        *   `price_trigger: float` (Optional, new trigger price)
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "order_id": "SHOONYA_ORDER_ID_123", 
          "message": "Order modified successfully."
        }
        ```
    *   **Output Schema (Error):**

*   **Tool Name:** `cancel_order`
    *   **Description:** Cancels an existing pending order.
    *   **Input Parameters:**
        *   `order_id: str` (The `norenordno` from Shoonya)
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "order_id": "SHOONYA_ORDER_ID_123",
          "message": "Order cancelled successfully."
        }
        ```
    *   **Output Schema (Error):**

### 4.3. Account Information Tools

*   **Tool Name:** `get_order_book`
    *   **Description:** Retrieves the order book for the current day.
    *   **Input Parameters:** None
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "orders": [ 
            { "order_id": "...", "tradingsymbol": "...", "status": "...", ... } 
          ]
        }
        ```
    *   **Output Schema (Error):**

*   **Tool Name:** `get_trade_book`
    *   **Description:** Retrieves the trade book for the current day.
    *   **Input Parameters:** None
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "trades": [ 
            { "order_id": "...", "trade_id": "...", "fill_price": "...", ... } 
          ]
        }
        ```
    *   **Output Schema (Error):**

*   **Tool Name:** `get_positions`
    *   **Description:** Retrieves current open positions.
    *   **Input Parameters:** None
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "positions": [ 
            { "tradingsymbol": "...", "net_quantity": "...", "pnl": "...", ... } 
          ]
        }
        ```
    *   **Output Schema (Error):**

*   **Tool Name:** `get_holdings`
    *   **Description:** Retrieves current holdings (stocks, etc.).
    *   **Input Parameters:** None
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "holdings": [ 
            { "tradingsymbol": "...", "quantity": "...", "average_price": "...", ... } 
          ]
        }
        ```
    *   **Output Schema (Error):**

*   **Tool Name:** `get_limits`
    *   **Description:** Retrieves account balance and limits.
    *   **Input Parameters:** None
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "limits": { "cash_margin": "...", "payin": "...", "m2m": "...", ... } 
        }
        ```
    *   **Output Schema (Error):**

### 4.4. Market Data Tools (Request/Response)

*   **Tool Name:** `search_scrip`
    *   **Description:** Searches for instrument tokens based on a search string.
    *   **Input Parameters:**
        *   `exchange: str`
        *   `search_text: str`
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "results": [ 
            { "exchange": "NSE", "token": "22", "tradingsymbol": "ACC-EQ", "symbolname": "ACC LIMITED" ... } 
          ]
        }
        ```
    *   **Output Schema (Error):**

*   **Tool Name:** `get_quotes`
    *   **Description:** Gets quotes (LTP, open, high, low, close, etc.) for specified instruments.
    *   **Input Parameters:**
        *   `exchange: str`
        *   `token: str` (instrument token)
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "quote": { "ltp": "...", "open": "...", "high": "...", "low": "...", "close": "...", "volume": "..." ... }
        }
        ```
    *   **Output Schema (Error):**

*   **Tool Name:** `get_option_chain`
    *   **Description:** Retrieves the option chain for a given underlying.
    *   **Input Parameters:**
        *   `exchange: str` (e.g., "NFO")
        *   `tradingsymbol: str` (e.g., "NIFTY", "BANKNIFTY")
        *   `strikeprice: float` (Optional, to get data around a specific strike)
        *   `count: int` (Optional, number of strikes to fetch around the `strikeprice` or ATM)
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "option_chain": [
            { "strike_price": "...", "ce_ltp": "...", "pe_ltp": "...", ... }
          ]
        }
        ```
    *   **Output Schema (Error):**

*   **Tool Name:** `get_time_price_series`
    *   **Description:** Fetches historical OHLCV candle data.
    *   **Input Parameters:**
        *   `exchange: str`
        *   `token: str` (instrument token)
        *   `start_time: int` (Unix timestamp)
        *   `end_time: int` (Unix timestamp)
        *   `interval: str` (e.g., "1", "5", "15", "D" for daily) - maps to Shoonya's `intrv`
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "candles": [
            { "time": "YYYY-MM-DD HH:MM:SS", "open": "...", "high": "...", "low": "...", "close": "...", "volume": "..." }
          ]
        }
        ```
    *   **Output Schema (Error):**

### 4.5. Market Data (Streaming/Subscription via MCP Resources - Conceptual)

*   **Tool Name:** `subscribe_market_feeds`
    *   **Description:** Subscribes to real-time market data feeds for a list of instruments. The actual data will be delivered via an MCP Resource.
    *   **Input Parameters:**
        *   `instruments: list[dict]` (List of instrument identifiers, e.g., `[{"exchange": "NSE", "token": "22"}, {"exchange": "NFO", "token": "35003"}]`)
        *   `feed_type: str` (Optional, e.g., "touchline", "depth". Defaults to "touchline". Shoonya might require specific subscription calls for different feed types, or it might be part of the instrument identifier itself if using specific pre-defined scrips for full depth.)
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "message": "Successfully subscribed to feeds for X instruments.",
          "subscription_id": "MCP_SUB_ID_XYZ" 
        }
        ```
    *   **Output Schema (Error):**
    *   **Side Effect:** The MCP server will internally call `ShoonyaApiPy.start_websocket()` (if not already started) and then use `ShoonyaApiPy.subscribe()` or `ShoonyaApiPy.subscribe_touchline()` for the given instruments. The received data will update the `market_data_feed_resource`.

*   **Tool Name:** `unsubscribe_market_feeds`
    *   **Description:** Unsubscribes from market data feeds.
    *   **Input Parameters:**
        *   `subscription_id: str` (Optional, the ID returned by `subscribe_market_feeds` to unsubscribe all instruments under that ID)
        *   `instruments: list[dict]` (Optional, list of specific instruments to unsubscribe if not using `subscription_id`)
    *   **Output Schema (Success):**
        ```json
        {
          "status": "success",
          "message": "Successfully unsubscribed from feeds."
        }
        ```
    *   **Output Schema (Error):**
    *   **Side Effect:** The MCP server will call `ShoonyaApiPy.unsubscribe()` for the specified instruments.

## 5. MCP Resources (Conceptual)

*   **Resource Name:** `market_data_feed_resource`
    *   **Description:** Provides access to live market data (ticks, depth if subscribed) for instruments the client has subscribed to using the `subscribe_market_feeds` tool.
    *   **How it's updated:** The MCP server will have a WebSocket message handler (`on_message`, `on_open`, `on_close`, `on_error` callbacks for `ShoonyaApiPy.start_websocket()`). When new market data is received from Shoonya via WebSocket, this handler will parse it and update the content of this MCP Resource. The resource could be structured as a dictionary where keys are instrument tokens (e.g., "NSE_22") and values are the latest tick data.
    *   **How LLM accesses:** The LLM client, following MCP specifications, would "read" this resource to get the latest snapshot of data or potentially "watch" it to receive updates as they arrive (if the MCP SDK and protocol support resource watching).

## 6. Error Handling

*   **General Approach:** The MCP server will catch errors from the `ShoonyaApi-py` library (which should ideally raise exceptions or return error codes/messages for failed API calls).
*   These Shoonya-specific errors will be translated into the standard MCP error JSON structure: `{"status": "error", "message": "Specific error details including Shoonya's message"}`.
*   HTTP status codes for tool responses should be managed by the MCP SDK (e.g., 200 for successful tool execution even if the result is a functional error like "insufficient funds", and 500 for server-side tool execution failures).

## 7. Configuration

*   **Shoonya API Credentials:** As mentioned in "Authentication Strategy", these (user ID, password, 2FA, vendor code, API secret, IMEI) will primarily be configured via environment variables.
*   **Logging:** Logging levels and output (console, file) should be configurable, perhaps via environment variables (e.g., `MCP_LOG_LEVEL=INFO`) or a simple configuration in the server startup script.
*   **Other Parameters:** Any other server-specific or `ShoonyaApiPy` client settings (e.g., timeouts, retry logic if applicable) could also be managed via environment variables or a config file.
```
