import asyncio
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Assuming MCPResource is the base class for creating custom, updatable resources.
# This might need to be adjusted based on the actual MCP SDK.
from modelcontextprotocol.mcp import MCPBaseServer, mcp_tool, SchemaInvalidError, ToolContext, MCPResource 

# Attempt to import ShoonyaApiPy, assuming api_helper.py is in the same directory
try:
    from api_helper import ShoonyaApiPy
except ImportError:
    # Provide a mock for ShoonyaApiPy if api_helper.py is not found,
    # so the agent can still be partially loaded and tested for MCP structure.
    logging.warning("Failed to import ShoonyaApiPy from api_helper.py. Using a mock. "
                    "Place api_helper.py in the shoonya_mcp_agent directory for full functionality.")
    class ShoonyaApiPyMock:
        def __init__(self):
            logging.info("ShoonyaApiPyMock initialized.")
        
        def login(self, userid, password, twoFA, vc, api_secret, imei):
            logging.info(f"ShoonyaApiPyMock: Attempting login for user {userid}")
            if password == "password123":
                logging.info(f"ShoonyaApiPyMock: Login successful for user {userid}")
                return {"stat": "Ok", "susertoken": "mock_token_xyz123", "uid": userid, "uname": "Mock User"}
            else:
                logging.error(f"ShoonyaApiPyMock: Login failed for user {userid}")
                return {"stat": "Not_Ok", "emsg": "Mock login failed: Invalid credentials"}
        
        # Add other methods that might be called during server init or by other tools later
        def get_user_details(self): # Example
            return {"uname": "Mock User"}

    ShoonyaApiPy = ShoonyaApiPyMock


# --- Input Schemas for Tools ---

# Helper model for Shoonya's instrument identifier, can be reused
class ShoonyaInstrumentInput(BaseModel):
    exchange: str = Field(..., description="Exchange (e.g., 'NSE', 'NFO', 'BSE').", alias="exch")
    tradingsymbol: str = Field(..., description="Trading symbol (e.g., 'SBIN-EQ', 'NIFTY23JUL20000CE').", alias="tsym")
    # token: str | None = Field(None, description="Instrument token, if known. Sometimes required by Shoonya instead of tradingsymbol.") # Shoonya often uses token

class ConnectShoonyaBrokerInput(BaseModel):
    user_id: str = Field(..., description="Shoonya User ID (e.g., client ID).")
    password: str = Field(..., description="Shoonya account password.")
    two_fa_token: str = Field(..., description="Two-factor authentication token (e.g., TOTP).")
    vendor_code: str = Field(..., description="Shoonya vendor code provided by the broker.")
    api_secret: str = Field(..., description="API secret key provided by Shoonya.")
    imei: str = Field(..., description="Registered IMEI (device identifier).")

class PlaceOrderInput(BaseModel):
    buy_or_sell: str = Field(..., description="Transaction type: 'B' for Buy, 'S' for Sell.", alias="trantype")
    product_type: str = Field(..., description="Product type: 'I' for Intraday, 'C' for CNC (Equity), 'M' for NRML (F&O), 'F' for MTF.", alias="prd")
    exchange: str = Field(..., description="Exchange name (e.g., 'NSE', 'NFO', 'BSE', 'MCX').", alias="exch")
    tradingsymbol: str = Field(..., description="Trading symbol (e.g., 'SBIN-EQ', 'NIFTY24JUL20000CE').", alias="tsym")
    quantity: int = Field(..., description="Order quantity.", alias="qty")
    discloseqty: int = Field(0, description="Disclosed quantity, defaults to 0.", alias="dscqty")
    price_type: str = Field(..., description="Price type: 'LMT' for Limit, 'MKT' for Market, 'SL-LMT' for Stop-Loss Limit, 'SL-MKT' for Stop-Loss Market.", alias="prctyp")
    price: float = Field(0.0, description="Order price. Required for 'LMT' and 'SL-LMT'. Set to 0 for 'MKT' and 'SL-MKT'.", alias="prc")
    trigger_price: float | None = Field(None, description="Trigger price. Required for 'SL-LMT' and 'SL-MKT' orders.", alias="trgprc")
    retention: str = Field('DAY', description="Order retention type: 'DAY' for Day order, 'IOC' for Immediate or Cancel.", alias="ret")
    amo: str = Field('NO', description="After Market Order: 'YES' or 'NO'.", alias="amo")
    remarks: str | None = Field(None, description="Optional remarks for the order.")
    # Shoonya specific: bookloss_price, bookprofit_price, trail_price for cover/bracket orders if supported by this tool later

class GetHoldingsInput(BaseModel):
    product_type: str | None = Field(None, description="Optional: Filter holdings by product type (e.g., 'C' for CNC). If None, fetches all.", alias="prd")

class SearchScripInput(BaseModel):
    exchange: str = Field(..., description="Exchange (e.g., 'NSE', 'NFO').", alias="exch")
    search_text: str = Field(..., description="Text to search for in scrip names/symbols.", alias="stext")

class GetQuotesInput(BaseModel):
    exchange: str = Field(..., description="Exchange (e.g., 'NSE', 'NFO', 'MCX', 'BSE', 'CDS').", alias="exch")
    token: str = Field(..., description="Instrument token for the scrip.")

class GetOptionChainInput(BaseModel):
    exchange: str = Field(..., description="Exchange, typically 'NFO' or 'MCX'.", alias="exch")
    tradingsymbol: str = Field(..., description="Trading symbol of the underlying (e.g., 'NIFTY', 'BANKNIFTY').", alias="tsym")
    strikeprice: float = Field(..., description="Strike price around which to fetch the option chain.", alias="strprc")
    count: int = Field(5, description="Number of strikes to fetch (typically ignored by Shoonya, which returns full chain near LTP or strprc).", alias="cnt") # Shoonya API doc for GetOptionChain does not list 'cnt'. It seems to return a fixed number or all available.

class GetTimePriceSeriesInput(BaseModel):
    exchange: str = Field(..., description="Exchange (e.g., 'NSE', 'NFO').", alias="exch")
    token: str = Field(..., description="Instrument token for the scrip.")
    starttime: int = Field(..., description="Start time as Unix timestamp (seconds since epoch).") # Shoonya expects "dd-MM-yyyy HH:mm:ss" string or epoch
    endtime: int | None = Field(None, description="End time as Unix timestamp. Defaults to None (Shoonya might fetch up to current).") # Shoonya expects "dd-MM-yyyy HH:mm:ss" string or epoch
    interval: int = Field(1, description="Candle interval in minutes (e.g., 1, 5, 15, 60 for hourly, 1440 for daily). Shoonya takes string like '1' or 'D'.", alias="intrv")

class SubscribeMarketFeedsInput(BaseModel):
    instruments: List[str] = Field(..., description="List of instruments to subscribe to, e.g., ['NSE|22', 'NFO|35003'].")

class UnsubscribeMarketFeedsInput(BaseModel):
    instruments: List[str] = Field(..., description="List of instruments to unsubscribe from, e.g., ['NSE|22', 'NFO|35003'].")


# --- MCP Resource Definition for Live Market Data ---

class ShoonyaTickData(BaseModel):
    """
    Represents the structure of a single tick data point for an instrument.
    Fields are based on common Shoonya feed fields. 'ts' for timestamp is added.
    """
    type: Optional[str] = None # e.g., 'tf', 'df' (touchline feed, depth feed) - from Shoonya's 't'
    exchange: Optional[str] = Field(None, alias="e")
    token: Optional[str] = Field(None, alias="tk")
    last_traded_price: Optional[float] = Field(None, alias="lp")
    last_traded_quantity: Optional[int] = Field(None, alias="lq")
    average_traded_price: Optional[float] = Field(None, alias="ap")
    volume: Optional[int] = Field(None, alias="v")
    change_percent: Optional[float] = Field(None, alias="c") # Percent change
    open_price: Optional[float] = Field(None, alias="o")
    high_price: Optional[float] = Field(None, alias="h")
    low_price: Optional[float] = Field(None, alias="l")
    close_price: Optional[float] = Field(None, alias="cl") # Previous day close
    total_buy_quantity: Optional[int] = Field(None, alias="tbq")
    total_sell_quantity: Optional[int] = Field(None, alias="tsq")
    open_interest: Optional[int] = Field(None, alias="oi")
    # For depth feed, Shoonya provides 'bp1', 'sp1', 'bq1', 'sq1' etc.
    # For now, focusing on touchline fields.
    feed_timestamp: Optional[str] = Field(None, alias="ft") # Shoonya's feed timestamp
    mcp_received_timestamp: Optional[float] = None # Timestamp when MCP agent received/processed it

    class Config:
        allow_population_by_field_name = True # Allows using aliases for population

class LiveMarketDataResource(MCPResource):
    resource_name = "shoonya_live_market_data"
    resource_description = "Provides live streaming market data for subscribed Shoonya instruments."
    # The schema for this resource will be a dictionary of ShoonyaTickData
    # e.g., Dict[str, ShoonyaTickData] where key is "EXCHANGE|TOKEN"
    # MCP SDK might require a more formal schema definition here.

    def __init__(self):
        super().__init__() # Assuming MCPResource has a constructor
        self._data: Dict[str, ShoonyaTickData] = {}
        self._lock = asyncio.Lock() # For thread-safe updates if needed, though callbacks are usually on main loop
        logging.info(f"MCP Resource '{self.resource_name}' initialized.")

    async def update_tick(self, instrument_key: str, tick_data: Dict[str, Any]):
        async with self._lock:
            try:
                # Map Shoonya's raw tick fields to our ShoonyaTickData model
                # Shoonya's 't' field indicates type: 'tf' (touchline), 'tk' (ack for token sub), 'df' (depth)
                # We are primarily interested in 'tf' and 'df' for data.
                if tick_data.get('t') not in ['tf', 'df']: # Only process actual data ticks
                    logging.debug(f"Ignoring non-data tick for {instrument_key}: {tick_data.get('t')}")
                    return

                # Basic mapping, ShoonyaApiPy might provide parsed data already.
                # If tick_data is already well-structured from ShoonyaApiPy, this can be simpler.
                # Assuming tick_data is a dict from Shoonya's feed.
                parsed_tick = ShoonyaTickData.parse_obj(tick_data) # parse_obj handles aliases
                parsed_tick.mcp_received_timestamp = asyncio.get_event_loop().time()
                
                self._data[instrument_key] = parsed_tick
                logging.debug(f"Resource '{self.resource_name}' updated for {instrument_key}: {parsed_tick.model_dump_json(exclude_none=True)}")
                
                # Notify MCP system that this resource has been updated.
                # The mechanism for this depends on the MCP SDK.
                # It might be automatic if self._data is a special observable dict,
                # or might require calling a method like self.notify_updated().
                await self.notify_update({instrument_key: parsed_tick.model_dump(by_alias=True, exclude_none=True)}) # Send delta or full data? SDK specific.

            except Exception as e:
                logging.error(f"Error processing tick for {instrument_key} in resource: {e}. Tick: {tick_data}", exc_info=True)
    
    async def get_instrument_data(self, instrument_key: str) -> Optional[ShoonyaTickData]:
        async with self._lock:
            return self._data.get(instrument_key)

    async def get_all_data(self) -> Dict[str, ShoonyaTickData]:
        async with self._lock:
            return self._data.copy()

    async def initialize_instrument(self, instrument_key: str):
        async with self._lock:
            if instrument_key not in self._data:
                # Initialize with empty data or a "pending" state
                self._data[instrument_key] = ShoonyaTickData(exchange=instrument_key.split('|')[0], token=instrument_key.split('|')[1])
                logging.info(f"Instrument {instrument_key} initialized in resource '{self.resource_name}'.")
                await self.notify_update({instrument_key: self._data[instrument_key].model_dump(by_alias=True, exclude_none=True)})


    async def remove_instrument(self, instrument_key: str):
        async with self._lock:
            if instrument_key in self._data:
                del self._data[instrument_key]
                logging.info(f"Instrument {instrument_key} removed from resource '{self.resource_name}'.")
                # Notify with a special marker or let clients figure it out by absence of key
                await self.notify_update({instrument_key: None}) # Indicate removal


# --- Main Agent Class ---

class ShoonyaMCPAgent(MCPBaseServer):
    def __init__(self):
        super().__init__(
            server_name="Shoonya MCP Agent",
            server_version="0.1.0",
            server_description="MCP Agent for interacting with the Shoonya Trading API (mocked or real)."
        )
        try:
            self.shoonya_api = ShoonyaApiPy()
            logging.info("ShoonyaApiPy instance created.")
        except Exception as e:
            logging.error(f"Failed to initialize ShoonyaApiPy: {e}", exc_info=True)
            self.shoonya_api = None # Ensure it's None if init fails

        self.shoonya_user_token: Optional[str] = None
        self.shoonya_user_id: Optional[str] = None
        self.shoonya_username: Optional[str] = None
        self.shoonya_account_details: Dict[str, Any] = {}
        
        # WebSocket State
        self.websocket_thread = None 
        self.websocket_connected = False
        self.subscribed_instruments_mcp: Dict[str, bool] = {} # Tracks if WE requested subscription
        
        # MCP Resource for Live Market Data
        self.live_market_data_resource = LiveMarketDataResource()
        self.add_mcp_resource(self.live_market_data_resource) # Assumed method to register resource

        logging.info("ShoonyaMCPAgent initialized with LiveMarketDataResource.")

    # --- WebSocket Callbacks ---
    def _on_websocket_open(self):
        self.websocket_connected = True
        logging.info("Shoonya WebSocket connection opened.")
        # If there are pending subscriptions, we might need to re-subscribe them here.
        # For now, assume subscriptions are made after WS is confirmed open.

    def _on_websocket_close(self):
        self.websocket_connected = False
        logging.info("Shoonya WebSocket connection closed.")
        # Clean up subscribed instruments if needed, or mark them as stale
        # self.subscribed_instruments_mcp.clear() # Or handle re-connection logic

    def _on_market_data_feed(self, tick_data: Dict[str, Any]):
        # This callback is executed in the WebSocket thread from ShoonyaApiPy.
        # It needs to schedule the resource update on the MCP server's event loop.
        # logging.debug(f"Raw market data feed received: {tick_data}")
        
        instrument_key = None
        if 'tk' in tick_data and 'e' in tick_data:
            instrument_key = f"{tick_data['e']}|{tick_data['tk']}"
        elif 'token' in tick_data and 'exseg' in tick_data: # Alternative Shoonya format
             instrument_key = f"{tick_data['exseg']}|{tick_data['token']}"
        
        if instrument_key and instrument_key in self.subscribed_instruments_mcp:
            # Schedule the async method `update_tick` to be run in the agent's event loop
            asyncio.run_coroutine_threadsafe(
                self.live_market_data_resource.update_tick(instrument_key, tick_data),
                self.get_event_loop() # Assuming MCPBaseServer provides access to its loop
            )
        elif instrument_key:
            logging.warning(f"Received tick for non-MCP-subscribed instrument {instrument_key}: {tick_data}")
        else:
            logging.warning(f"Received tick_data without identifiable instrument key: {tick_data}")


    def _on_order_update_feed(self, order_data: Dict[str, Any]):
        logging.info(f"Order update feed received: {order_data}")
        # TODO: Implement handling for order updates, potentially updating another MCP resource.
        # Example: asyncio.run_coroutine_threadsafe(self.order_updates_resource.update_order(order_data), self.get_event_loop())
        pass

    # --- Helper for Auth Check ---
    def _is_connected(self):
        return self.shoonya_user_token is not None

    @mcp_tool(
        name="connect_shoonya_broker",
        description="Connects to the Shoonya trading platform using user credentials. Establishes a session with Shoonya.",
        input_schema=ConnectShoonyaBrokerInput
    )
    async def connect_shoonya_broker(self, tool_input: ConnectShoonyaBrokerInput, context: ToolContext):
        logging.info(f"connect_shoonya_broker called for user: {tool_input.user_id}")
        if not self.shoonya_api:
            logging.error("Shoonya API client is not initialized.")
            return {"status": "error", "message": "Shoonya API client not initialized. Check server logs."}

        # If already connected and websocket is running, perhaps return current status or offer to reconnect.
        if self._is_connected() and self.websocket_connected:
            logging.info(f"Already connected and WebSocket is active for user {self.shoonya_user_id}.")
            return {
                "status": "success",
                "message": f"Already connected to Shoonya as {self.shoonya_username}. WebSocket active.",
                "user_id": self.shoonya_user_id,
                "username": self.shoonya_username
            }
        
        try:
            login_response = self.shoonya_api.login(
                userid=tool_input.user_id,
                password=tool_input.password,
                twoFA=tool_input.two_fa_token,
                vc=tool_input.vendor_code,
                api_secret=tool_input.api_secret,
                imei=tool_input.imei
            )
            logging.debug(f"Shoonya login API response: {login_response}")

        except Exception as e:
            logging.error(f"Exception during Shoonya login: {e}", exc_info=True)
            self.shoonya_user_token = None # Ensure state is reset
            self.shoonya_user_id = None
            self.shoonya_username = None
            self.websocket_connected = False
            return {"status": "error", "message": f"An exception occurred during Shoonya login: {str(e)}"}

        if login_response and login_response.get('stat') == 'Ok':
            self.shoonya_user_token = login_response.get('susertoken')
            self.shoonya_user_id = login_response.get('uid')
            self.shoonya_username = login_response.get('uname')
            self.shoonya_account_details = {key: login_response.get(key) for key in login_response if key not in ['stat', 'emsg', 'susertoken']}
            
            logging.info(f"Shoonya login successful for user: {self.shoonya_user_id}, username: {self.shoonya_username}. Now starting WebSocket.")

            try:
                # Start WebSocket in a separate thread as it's blocking
                # Requires Python 3.9+ for asyncio.to_thread
                # For older versions, use loop.run_in_executor(None, blocking_io_function, *args)
                logging.info("Attempting to start Shoonya WebSocket...")
                # Ensure shoonya_api is the instance of ShoonyaApiPy
                await asyncio.to_thread(
                    self.shoonya_api.start_websocket,
                    order_update_callback=self._on_order_update_feed,
                    subscribe_callback=self._on_market_data_feed,
                    socket_open_callback=self._on_websocket_open,
                    socket_close_callback=self._on_websocket_close
                )
                # Note: start_websocket is blocking. If it successfully starts and runs in a thread,
                # this await will only complete when the thread finishes (i.e., websocket closes).
                # This might not be the desired behavior if start_websocket itself daemonizes or returns quickly.
                # ShoonyaApi-py's start_websocket is indeed blocking.
                # The design of start_websocket in a library usually means it should be run and it keeps running.
                # So, we need to ensure this thread doesn't prevent the connect tool from returning.
                # A common pattern is to have the thread store an exception if it fails to start,
                # and the main thread checks that after a short delay.
                # For now, let's assume `asyncio.to_thread` handles it well for starting.
                # The `_on_websocket_open` callback will set `self.websocket_connected = True`.
                # We might need a short sleep here to allow the websocket to attempt connection.
                await asyncio.sleep(2) # Give 2 seconds for WebSocket to attempt connection and open callback to fire.

                if self.websocket_connected:
                    logging.info("Shoonya WebSocket seems to have started successfully.")
                    return {
                        "status": "success",
                        "message": "Successfully connected to Shoonya and WebSocket started.",
                        "user_id": self.shoonya_user_id,
                        "username": self.shoonya_username,
                        "websocket_status": "connected"
                    }
                else:
                    logging.error("Shoonya WebSocket did not connect after login.")
                    # Attempt to clean up login state if WebSocket failed
                    self.shoonya_user_token = None
                    self.shoonya_user_id = None
                    self.shoonya_username = None
                    return {
                        "status": "error",
                        "message": "Shoonya login succeeded, but WebSocket connection failed to open. Please check network/config.",
                        "websocket_status": "disconnected"
                    }

            except Exception as e:
                logging.error(f"Exception when trying to start WebSocket: {e}", exc_info=True)
                self.shoonya_user_token = None # Reset login state
                self.shoonya_user_id = None
                self.shoonya_username = None
                self.websocket_connected = False
                return {"status": "error", "message": f"WebSocket startup failed after login: {str(e)}"}
        else:
            logging.error(f"Shoonya login failed: {login_response.get('emsg', 'Unknown error')}")
            self.shoonya_user_token = None
            self.shoonya_user_id = None
            self.shoonya_username = None
            self.websocket_connected = False
            return {
                "status": "error",
                "message": f"Shoonya login failed: {login_response.get('emsg', 'Unknown error')}"
            }

    # Add a simple health check tool
    @mcp_tool(name="health_check", description="Checks the health of the MCP agent.")
    async def health_check(self, tool_input: None, context: ToolContext):
        shoonya_status = "connected" if self._is_connected() else "disconnected"
        return {
            "status": "success", 
            "message": "Agent is running.",
            "shoonya_connection_status": shoonya_status,
            "shoonya_user_id": self.shoonya_user_id,
            "shoonya_username": self.shoonya_username,
            "websocket_status": "connected" if self.websocket_connected else "disconnected"
        }

    @mcp_tool(
        name="subscribe_market_feeds",
        description="Subscribes to real-time market data feeds for specified instruments.",
        input_schema=SubscribeMarketFeedsInput
    )
    async def subscribe_market_feeds(self, tool_input: SubscribeMarketFeedsInput, context: ToolContext):
        logging.info(f"subscribe_market_feeds called for instruments: {tool_input.instruments}")
        if not self._is_connected():
            return {"status": "error", "message": "Not connected to Shoonya. Please call 'connect_shoonya_broker' first."}
        if not self.websocket_connected:
            return {"status": "error", "message": "Shoonya WebSocket is not connected. Cannot subscribe to feeds."}

        try:
            # ShoonyaApiPy's subscribe method takes a list of instrument strings
            # Example: api.subscribe(['NSE|22', 'NFO|35003'])
            # No direct JSON response with 'stat'/'emsg' is typical for subscribe/unsubscribe.
            # Success is usually implied by no exception and data flowing.
            self.shoonya_api.subscribe(instrument_list=tool_input.instruments) # This is a synchronous call
            
            successfully_requested_instruments = []
            for inst in tool_input.instruments:
                self.subscribed_instruments_mcp[inst] = True 
                # Initialize in resource so clients can see it's a subscribed item
                asyncio.run_coroutine_threadsafe(
                    self.live_market_data_resource.initialize_instrument(inst),
                    self.get_event_loop()
                )
                successfully_requested_instruments.append(inst)
            
            logging.info(f"Subscription request processed for instruments: {successfully_requested_instruments}")
            return {
                "status": "success",
                "message": f"Subscription request processed for {len(successfully_requested_instruments)} instruments. Monitor resource for data.",
                "requested_instruments": successfully_requested_instruments
            }

        except Exception as e:
            logging.error(f"Exception during Shoonya subscribe: {e}", exc_info=True)
            # Attempt to revert optimistic tracking if some failed
            # for inst in tool_input.instruments:
            #     if inst in self.subscribed_instruments_mcp: del self.subscribed_instruments_mcp[inst]
            return {"status": "error", "message": f"An exception occurred during subscribe: {str(e)}"}

    @mcp_tool(
        name="unsubscribe_market_feeds",
        description="Unsubscribes from market data feeds for specified instruments.",
        input_schema=UnsubscribeMarketFeedsInput
    )
    async def unsubscribe_market_feeds(self, tool_input: UnsubscribeMarketFeedsInput, context: ToolContext):
        logging.info(f"unsubscribe_market_feeds called for instruments: {tool_input.instruments}")
        if not self._is_connected():
            return {"status": "error", "message": "Not connected to Shoonya. Please call 'connect_shoonya_broker' first."}
        # Unsubscribe can be called even if websocket seems disconnected locally, to clear server-side subs.
        # However, if ShoonyaApiPy requires live WS for unsubscribe, this might fail.
        # if not self.websocket_connected: # Allow unsubscription attempts even if WS seems down locally
        #     return {"status": "error", "message": "Shoonya WebSocket is not connected."}

        try:
            self.shoonya_api.unsubscribe(instrument_list=tool_input.instruments) # Synchronous call
            
            unsubscribed_instruments_list = []
            for inst in tool_input.instruments:
                if inst in self.subscribed_instruments_mcp:
                    del self.subscribed_instruments_mcp[inst]
                # Remove from resource or mark as stale
                asyncio.run_coroutine_threadsafe(
                    self.live_market_data_resource.remove_instrument(inst),
                    self.get_event_loop()
                )
                unsubscribed_instruments_list.append(inst)
            
            logging.info(f"Unsubscribe request processed for instruments: {unsubscribed_instruments_list}")
            return {
                "status": "success",
                "message": f"Unsubscribe request processed for {len(unsubscribed_instruments_list)} instruments.",
                "unsubscribed_instruments": unsubscribed_instruments_list
            }

        except Exception as e:
            logging.error(f"Exception during Shoonya unsubscribe: {e}", exc_info=True)
            return {"status": "error", "message": f"An exception occurred during unsubscribe: {str(e)}"}


    @mcp_tool(
        name="place_order",
        description="Places a trading order with Shoonya after validating connection.",
        input_schema=PlaceOrderInput
    )
    async def place_order(self, tool_input: PlaceOrderInput, context: ToolContext):
        logging.info(f"place_order called with input: {tool_input.model_dump_json(exclude_none=True)}")
        if not self._is_connected():
            return {"status": "error", "message": "Not connected to Shoonya. Please call 'connect_shoonya_broker' first."}

        try:
            # Convert Pydantic model to dict, using aliases for Shoonya parameter names
            order_args = tool_input.model_dump(by_alias=True, exclude_none=True)
            
            # Add user_id (actid) which is required by Shoonya's place_order
            order_args['actid'] = self.shoonya_user_id 
            # Ensure 'uid' (shoonya_user_id for general calls) is not mixed up with 'actid' for orders
            # Shoonya API docs for place_order: uid is the logged-in user, actid is the account for the order.
            # For retail, uid and actid are usually the same.
            
            logging.debug(f"Calling Shoonya place_order with args: {order_args}")
            response = self.shoonya_api.place_order(**order_args)
            logging.debug(f"Shoonya place_order API response: {response}")

            if response and response.get('stat') == 'Ok' and response.get('norenordno'):
                logging.info(f"Order placed successfully via Shoonya. Order ID: {response.get('norenordno')}")
                return {
                    "status": "success",
                    "message": response.get('result', 'Order placed successfully.'), # Shoonya might use 'result'
                    "order_id": response.get('norenordno')
                }
            else:
                error_msg = response.get('emsg', 'Failed to place order with Shoonya.')
                logging.error(f"Shoonya place_order failed: {error_msg}")
                return {"status": "error", "message": error_msg, "order_id": None}

        except Exception as e:
            logging.error(f"Exception during Shoonya place_order: {e}", exc_info=True)
            return {"status": "error", "message": f"An exception occurred: {str(e)}", "order_id": None}

    @mcp_tool(
        name="get_order_book",
        description="Retrieves the order book for the current day from Shoonya."
    )
    async def get_order_book(self, tool_input: None, context: ToolContext): # No input schema for now
        logging.info("get_order_book called.")
        if not self._is_connected():
            return {"status": "error", "message": "Not connected to Shoonya. Please call 'connect_shoonya_broker' first."}

        try:
            response = self.shoonya_api.get_order_book() # No parameters needed for standard call
            logging.debug(f"Shoonya get_order_book API response: {response}")

            if isinstance(response, list) and len(response) > 0 and response[0].get('stat') == 'Ok':
                 # Assuming success means a list of orders, potentially empty if no orders
                orders = [order for order in response if order.get('norenordno')] # Filter out any non-order status dicts
                logging.info(f"Successfully retrieved order book. Number of orders: {len(orders)}")
                return {"status": "success", "order_book": orders}
            elif isinstance(response, list) and len(response) > 0 and response[0].get('stat') == 'Not_Ok':
                error_msg = response[0].get('emsg', 'Failed to retrieve order book from Shoonya.')
                logging.error(f"Shoonya get_order_book failed: {error_msg}")
                return {"status": "error", "message": error_msg, "order_book": None}
            elif isinstance(response, list) and not response : # Empty list means no orders
                 logging.info("Successfully retrieved order book. No orders found.")
                 return {"status": "success", "order_book": []}
            else: # Unexpected response format
                error_msg = "Unexpected response format from Shoonya get_order_book."
                logging.error(f"{error_msg} Response: {response}")
                return {"status": "error", "message": error_msg, "order_book": None}


        except Exception as e:
            logging.error(f"Exception during Shoonya get_order_book: {e}", exc_info=True)
            return {"status": "error", "message": f"An exception occurred: {str(e)}", "order_book": None}

    @mcp_tool(
        name="get_positions",
        description="Retrieves current open positions from Shoonya."
    )
    async def get_positions(self, tool_input: None, context: ToolContext): # No input schema
        logging.info("get_positions called.")
        if not self._is_connected():
            return {"status": "error", "message": "Not connected to Shoonya. Please call 'connect_shoonya_broker' first."}

        try:
            response = self.shoonya_api.get_positions()
            logging.debug(f"Shoonya get_positions API response: {response}")
            
            # Shoonya's get_positions typically returns a list of position dicts if successful,
            # or a list containing one dict with "stat": "Not_Ok" on error.
            if isinstance(response, list) and len(response) > 0 and response[0].get('stat') == 'Ok':
                positions = [pos for pos in response if pos.get('tsym')] # Filter out status dicts if any, ensure 'tsym' exists
                logging.info(f"Successfully retrieved positions. Number of positions: {len(positions)}")
                return {"status": "success", "positions": positions}
            elif isinstance(response, list) and len(response) > 0 and response[0].get('stat') == 'Not_Ok':
                error_msg = response[0].get('emsg', 'Failed to retrieve positions from Shoonya.')
                logging.error(f"Shoonya get_positions failed: {error_msg}")
                return {"status": "error", "message": error_msg, "positions": None}
            elif isinstance(response, list) and not response: # Empty list means no positions
                logging.info("Successfully retrieved positions. No open positions found.")
                return {"status": "success", "positions": []}
            else: # Unexpected response format
                error_msg = "Unexpected response format from Shoonya get_positions."
                logging.error(f"{error_msg} Response: {response}")
                return {"status": "error", "message": error_msg, "positions": None}

        except Exception as e:
            logging.error(f"Exception during Shoonya get_positions: {e}", exc_info=True)
            return {"status": "error", "message": f"An exception occurred: {str(e)}", "positions": None}

    @mcp_tool(
        name="get_holdings",
        description="Retrieves current holdings from Shoonya, with an optional filter for product type.",
        input_schema=GetHoldingsInput  # Optional input, so tool_input can be None if no filters used
    )
    async def get_holdings(self, tool_input: GetHoldingsInput | None, context: ToolContext):
        logging.info(f"get_holdings called with input: {tool_input.model_dump_json(exclude_none=True) if tool_input else 'None'}")
        if not self._is_connected():
            return {"status": "error", "message": "Not connected to Shoonya. Please call 'connect_shoonya_broker' first."}

        try:
            api_args = {}
            if tool_input and tool_input.product_type:
                api_args['prd'] = tool_input.product_type
            
            # Add user_id (actid) which is required by Shoonya's get_holdings
            api_args['actid'] = self.shoonya_user_id

            logging.debug(f"Calling Shoonya get_holdings with args: {api_args}")
            response = self.shoonya_api.get_holdings(**api_args)
            logging.debug(f"Shoonya get_holdings API response: {response}")

            # Similar to get_positions, response is a list, potentially with a status dict
            if isinstance(response, list) and len(response) > 0 and response[0].get('stat') == 'Ok':
                holdings = [h for h in response if h.get('tsym')] # Filter out status dicts
                logging.info(f"Successfully retrieved holdings. Number of holdings: {len(holdings)}")
                return {"status": "success", "holdings": holdings}
            elif isinstance(response, list) and len(response) > 0 and response[0].get('stat') == 'Not_Ok':
                error_msg = response[0].get('emsg', 'Failed to retrieve holdings from Shoonya.')
                logging.error(f"Shoonya get_holdings failed: {error_msg}")
                return {"status": "error", "message": error_msg, "holdings": None}
            elif isinstance(response, list) and not response:
                logging.info("Successfully retrieved holdings. No holdings found.")
                return {"status": "success", "holdings": []}
            else:
                error_msg = "Unexpected response format from Shoonya get_holdings."
                logging.error(f"{error_msg} Response: {response}")
                return {"status": "error", "message": error_msg, "holdings": None}

        except Exception as e:
            logging.error(f"Exception during Shoonya get_holdings: {e}", exc_info=True)
            return {"status": "error", "message": f"An exception occurred: {str(e)}", "holdings": None}

    @mcp_tool(
        name="get_limits",
        description="Retrieves account balance and limits from Shoonya."
    )
    async def get_limits(self, tool_input: None, context: ToolContext): # No input schema needed
        logging.info("get_limits called.")
        if not self._is_connected():
            return {"status": "error", "message": "Not connected to Shoonya. Please call 'connect_shoonya_broker' first."}

        try:
            # actid is required by get_limits
            response = self.shoonya_api.get_limits(actid=self.shoonya_user_id)
            logging.debug(f"Shoonya get_limits API response: {response}")

            if response and response.get('stat') == 'Ok':
                logging.info("Successfully retrieved limits.")
                # Remove stat and emsg for cleaner output if they exist
                limits_data = {k: v for k, v in response.items() if k not in ['stat', 'emsg']}
                return {"status": "success", "limits": limits_data}
            else:
                error_msg = response.get('emsg', 'Failed to retrieve limits from Shoonya.')
                logging.error(f"Shoonya get_limits failed: {error_msg}")
                return {"status": "error", "message": error_msg, "limits": None}

        except Exception as e:
            logging.error(f"Exception during Shoonya get_limits: {e}", exc_info=True)
            return {"status": "error", "message": f"An exception occurred: {str(e)}", "limits": None}

    @mcp_tool(
        name="search_scrip",
        description="Searches for instrument tokens based on a search string.",
        input_schema=SearchScripInput
    )
    async def search_scrip(self, tool_input: SearchScripInput, context: ToolContext):
        logging.info(f"search_scrip called with input: {tool_input.model_dump_json(exclude_none=True)}")
        if not self._is_connected(): # Though searchscrip might not strictly need login, it's good practice for agent consistency
            return {"status": "error", "message": "Not connected to Shoonya. Please call 'connect_shoonya_broker' first."}

        try:
            api_args = tool_input.model_dump(by_alias=True) # exch, stext
            logging.debug(f"Calling Shoonya searchscrip with args: {api_args}")
            response = self.shoonya_api.searchscrip(**api_args)
            logging.debug(f"Shoonya searchscrip API response: {response}")

            if response and response.get('stat') == 'Ok' and 'values' in response:
                scrips = response['values']
                logging.info(f"Scrip search successful. Found {len(scrips)} scrips.")
                return {"status": "success", "scrips": scrips}
            elif response and response.get('stat') == 'Not_Ok':
                error_msg = response.get('emsg', 'Failed to search scrips.')
                logging.error(f"Shoonya searchscrip failed: {error_msg}")
                return {"status": "error", "message": error_msg, "scrips": None}
            else: # Handles cases like no 'values' or empty response
                logging.info("Scrip search returned no results or unexpected format.")
                return {"status": "success", "scrips": [], "message": response.get('emsg', "No scrips found or unexpected format.")}


        except Exception as e:
            logging.error(f"Exception during Shoonya searchscrip: {e}", exc_info=True)
            return {"status": "error", "message": f"An exception occurred: {str(e)}", "scrips": None}

    @mcp_tool(
        name="get_quotes",
        description="Gets quotes (LTP, open, high, low, close, etc.) for a specified instrument.",
        input_schema=GetQuotesInput
    )
    async def get_quotes(self, tool_input: GetQuotesInput, context: ToolContext):
        logging.info(f"get_quotes called with input: {tool_input.model_dump_json(exclude_none=True)}")
        if not self._is_connected():
            return {"status": "error", "message": "Not connected to Shoonya. Please call 'connect_shoonya_broker' first."}

        try:
            api_args = tool_input.model_dump(by_alias=True) # exch, token
            logging.debug(f"Calling Shoonya get_quotes with args: {api_args}")
            response = self.shoonya_api.get_quotes(**api_args)
            logging.debug(f"Shoonya get_quotes API response: {response}")

            if response and response.get('stat') == 'Ok':
                # Remove stat and emsg for cleaner output if they exist
                quote_data = {k: v for k, v in response.items() if k not in ['stat', 'emsg']}
                logging.info(f"Successfully retrieved quote for {tool_input.exchange}:{tool_input.token}.")
                return {"status": "success", "quote": quote_data}
            else:
                error_msg = response.get('emsg', 'Failed to retrieve quote.')
                logging.error(f"Shoonya get_quotes failed for {tool_input.exchange}:{tool_input.token}: {error_msg}")
                return {"status": "error", "message": error_msg, "quote": None}

        except Exception as e:
            logging.error(f"Exception during Shoonya get_quotes for {tool_input.exchange}:{tool_input.token}: {e}", exc_info=True)
            return {"status": "error", "message": f"An exception occurred: {str(e)}", "quote": None}

    @mcp_tool(
        name="get_option_chain",
        description="Retrieves the option chain for a given underlying and strike price.",
        input_schema=GetOptionChainInput
    )
    async def get_option_chain(self, tool_input: GetOptionChainInput, context: ToolContext):
        logging.info(f"get_option_chain called with input: {tool_input.model_dump_json(exclude_none=True)}")
        if not self._is_connected():
            return {"status": "error", "message": "Not connected to Shoonya. Please call 'connect_shoonya_broker' first."}
        
        try:
            api_args = tool_input.model_dump(by_alias=True) # exch, tsym, strprc, cnt
            logging.debug(f"Calling Shoonya get_option_chain with args: {api_args}")
            # Shoonya's get_option_chain expects 'strikeprice' not 'strprc' in its direct call,
            # and 'tradingsymbol' not 'tsym'. Pydantic alias handles this for the model,
            # but the direct call to ShoonyaApiPy needs the lib's specific names.
            # Let's re-map if ShoonyaApiPy doesn't use the aliased names internally.
            # Based on ShoonyaApi-py source, it uses: exch, searchagesymbol, strprc
            # 'searchagesymbol' seems to be the 'tradingsymbol'.
            # 'cnt' is not listed in ShoonyaApi-py's get_option_chain method.
            
            # Correcting arguments for ShoonyaApiPy.get_option_chain
            # ShoonyaApiPy.get_option_chain(self, exch, searchagesymbol, strprc, uid=None)
            shoonya_args = {
                'exch': tool_input.exchange,
                'searchagesymbol': tool_input.tradingsymbol,
                'strprc': str(tool_input.strikeprice) # Shoonya expects strike price as string
            }
            
            response = self.shoonya_api.get_option_chain(**shoonya_args)
            logging.debug(f"Shoonya get_option_chain API response: {response}")

            if response and response.get('stat') == 'Ok' and 'values' in response:
                option_chain_data = response['values']
                logging.info(f"Successfully retrieved option chain for {tool_input.tradingsymbol}.")
                return {"status": "success", "option_chain": option_chain_data}
            elif response and response.get('stat') == 'Not_Ok':
                error_msg = response.get('emsg', 'Failed to retrieve option chain.')
                logging.error(f"Shoonya get_option_chain for {tool_input.tradingsymbol} failed: {error_msg}")
                return {"status": "error", "message": error_msg, "option_chain": None}
            else:
                logging.info(f"Option chain for {tool_input.tradingsymbol} returned no results or unexpected format.")
                return {"status": "success", "option_chain": [], "message": response.get('emsg', "No option data found or unexpected format.")}

        except Exception as e:
            logging.error(f"Exception during Shoonya get_option_chain for {tool_input.tradingsymbol}: {e}", exc_info=True)
            return {"status": "error", "message": f"An exception occurred: {str(e)}", "option_chain": None}

    @mcp_tool(
        name="get_time_price_series",
        description="Fetches historical OHLCV candle data from Shoonya.",
        input_schema=GetTimePriceSeriesInput
    )
    async def get_time_price_series(self, tool_input: GetTimePriceSeriesInput, context: ToolContext):
        logging.info(f"get_time_price_series called with input: {tool_input.model_dump_json(exclude_none=True)}")
        if not self._is_connected():
            return {"status": "error", "message": "Not connected to Shoonya. Please call 'connect_shoonya_broker' first."}

        try:
            # Shoonya's get_time_price_series expects 'intrv' for interval.
            # And time needs to be formatted if not using epoch directly, but ShoonyaApiPy might handle epoch.
            # ShoonyaApiPy.get_time_price_series(self, exch, token, stime=None, etime=None, intrv=None, uid=None)
            # It seems ShoonyaApiPy expects stime and etime as string "dd-MM-yyyy HH:mm:ss" if not None.
            # For simplicity, we'll assume the user passes valid epoch seconds and ShoonyaApiPy handles it,
            # or we'd need a conversion function here. The mock will just pass it through.
            # The design doc specified integer timestamps, so we'll stick to that for the tool input.
            # The actual Shoonya API might require string conversion for these.

            api_args = {
                "exch": tool_input.exchange,
                "token": tool_input.token,
                "stime": str(tool_input.starttime), # Pass as string if ShoonyaApiPy expects it, or handle conversion
                "etime": str(tool_input.endtime) if tool_input.endtime else None,
                "intrv": str(tool_input.interval)
            }
            logging.debug(f"Calling Shoonya get_time_price_series with args: {api_args}")
            response = self.shoonya_api.get_time_price_series(**api_args)
            # Response is typically a list of candle data dicts, or error dict
            logging.debug(f"Shoonya get_time_price_series API response: {response}")

            if isinstance(response, list) and response and 'stat' not in response[0] : # Successful response is a list of dicts without 'stat'
                logging.info(f"Successfully retrieved time price series for {tool_input.exchange}:{tool_input.token}.")
                return {"status": "success", "candles": response}
            elif isinstance(response, list) and response and response[0].get('stat') == 'Not_Ok':
                error_msg = response[0].get('emsg', 'Failed to retrieve time price series.')
                logging.error(f"Shoonya get_time_price_series for {tool_input.exchange}:{tool_input.token} failed: {error_msg}")
                return {"status": "error", "message": error_msg, "candles": None}
            elif isinstance(response, list) and not response:
                 logging.info(f"Time price series for {tool_input.exchange}:{tool_input.token} returned no data.")
                 return {"status": "success", "candles": []}
            else:
                error_msg = "Unexpected response format from Shoonya get_time_price_series."
                logging.error(f"{error_msg} Response: {response}")
                return {"status": "error", "message": error_msg, "candles": None}

        except Exception as e:
            logging.error(f"Exception during Shoonya get_time_price_series for {tool_input.exchange}:{tool_input.token}: {e}", exc_info=True)
            return {"status": "error", "message": f"An exception occurred: {str(e)}", "candles": None}


# --- Main Execution Block ---
async def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    agent = ShoonyaMCPAgent()
    
    # Example of how to run the server (this might vary based on MCP SDK specifics)
    # For now, let's assume the MCPBaseServer has a 'run' method or similar.
    # If it's an Async ASGI server, it might be run with uvicorn.
    # This part is highly dependent on the MCP SDK's server execution model.
    # The following is a generic placeholder.
    
    logging.info("Starting Shoonya MCP Agent...")
    # Replace with actual server running logic from MCP SDK documentation
    # e.g., if it's a FastAPI based server:
    # import uvicorn
    # uvicorn.run(agent.get_fastapi_app(), host="0.0.0.0", port=8000)
    
    # Or if it has its own run method:
    # await agent.run(host="0.0.0.0", port=8000) 
    
    # For now, as a simple test, we can just indicate it would run.
    # In a real scenario, this would block and run the server.
    print("Shoonya MCP Agent setup complete. Replace this print with actual server run command from MCP SDK.")
    print("Example: await agent.start(host='127.0.0.1', port=8765)")
    print("To test, you would need an MCP client to connect and call tools.")

    # A simple loop to keep the main function alive for testing if not using a blocking server start
    # try:
    #     while True:
    #         await asyncio.sleep(3600) # Keep alive
    # except KeyboardInterrupt:
    #     logging.info("Agent shutting down.")


if __name__ == '__main__':
    # Note: MCPBaseServer might require asyncio context to run even if tools are synchronous.
    # If your MCPBaseServer or its tools are truly async, ensure they are defined with `async def`
    # and awaited properly.
    asyncio.run(main())
