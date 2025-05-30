# Shoonya MCP Server (Mock)

## Description

This project is a mock Market Connectivity Protocol (MCP) server designed to simulate interactions with a Shoonya-like trading API. It provides a basic framework for testing client applications that would connect to Shoonya for order placement and market data.

**Note:** This is a **mock server**. All interactions with the "Shoonya API" are simulated through placeholder functions. No actual trading or connection to live Shoonya systems occurs.

## Key Features

*   **Authentication:**
    *   `/connect` endpoint for client authentication.
    *   Simulates Shoonya login and returns an MCP-specific session token.
*   **Order Management:**
    *   `/order` endpoint for placing trading orders.
    *   Comprehensive validation of order parameters (data types, allowed values for exchange, order type, etc.).
    *   Basic pre-trade risk checks (maximum order quantity, maximum order value for LIMIT/SL orders).
    *   Returns mock responses from the "broker," including order status.
*   **Market Data (Mock):**
    *   `/marketdata/subscribe` endpoint to simulate subscribing to instrument data.
    *   `/marketdata/fetch` endpoint to retrieve mock market data for subscribed instruments.
    *   Simulated data includes LTP, volume, OHLC, and changes randomly on fetch to mimic a live feed.
*   **API Definition:**
    *   A detailed API definition is available in `mcp_server_api_definition.md`.

## Setup and Running

1.  **Prerequisites:**
    *   Python 3.x
    *   pip (Python package installer)

2.  **Installation:**
    *   Clone the repository (if you haven't already).
    *   Navigate to the project directory.
    *   Install the required dependencies:
        ```bash
        pip install -r requirements.txt
        ```

3.  **Running the Server:**
    *   To start the Flask development server:
        ```bash
        python mcp_server/app.py
        ```
    *   The server will typically start on `http://127.0.0.1:5000/`.

## API Endpoints Overview

*   `POST /connect`: Authenticate and get a session token.
*   `POST /order`: Place a new order. Requires Bearer token.
*   `POST /marketdata/subscribe`: Subscribe to mock market data. Requires Bearer token.
*   `GET /marketdata/fetch`: Fetch mock market data for subscriptions. Requires Bearer token.

Refer to `mcp_server_api_definition.md` for detailed request/response formats.

## Current Status

*   The server is a **mock implementation** intended for development and testing of client applications.
*   All interactions that would normally go to the Shoonya trading platform are handled by placeholder functions within `mcp_server/app.py`.
*   No real financial transactions occur.
*   Further development would be required to integrate with the actual Shoonya API.
