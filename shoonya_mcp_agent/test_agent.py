import asyncio
import unittest
from unittest.mock import patch, MagicMock, ANY

from modelcontextprotocol.mcp import ToolContext

# Make sure 'shoonya_mcp_agent' is in the Python path or adjust import accordingly
# For example, if running from the parent directory of shoonya_mcp_agent:
# import sys
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shoonya_mcp_agent.agent import (
    ShoonyaMCPAgent, 
    ConnectShoonyaBrokerInput, 
    LiveMarketDataResource, 
    ShoonyaTickData,
    PlaceOrderInput # Added for the new test class
)

class TestShoonyaMCPAgentConnect(unittest.IsolatedAsyncioTestCase):

    def _get_default_connect_input(self):
        return ConnectShoonyaBrokerInput(
            user_id="test_user",
            password="test_password",
            two_fa_token="123456",
            vendor_code="test_vendor",
            api_secret="test_secret",
            imei="test_imei"
        )

    @patch('shoonya_mcp_agent.agent.ShoonyaApiPy')
    async def test_connect_shoonya_broker_success(self, MockShoonyaApiPyClass):
        mock_api_instance = MockShoonyaApiPyClass.return_value
        mock_api_instance.login.return_value = {
            "stat": "Ok", "susertoken": "mock_token_xyz", "uid": "test_uid", "uname": "Test User"
        }

        agent = ShoonyaMCPAgent()
        # agent.shoonya_api is already an instance of the mock due to the class-level patch
        # if ShoonyaApiPy was instantiated elsewhere, we might need agent.shoonya_api = mock_api_instance

        # Mock for start_websocket: it needs to call the open callback to simulate successful connection
        def mock_start_websocket_sync(order_update_callback, subscribe_callback, socket_open_callback, socket_close_callback):
            logging.info("mock_start_websocket_sync called")
            if socket_open_callback:
                socket_open_callback() # Simulate WebSocket opening
            # In a real scenario, this function would block. Here it just calls the callback.
        
        mock_api_instance.start_websocket = MagicMock(side_effect=mock_start_websocket_sync)

        test_input = self._get_default_connect_input()
        mock_context = MagicMock(spec=ToolContext)

        response = await agent.connect_shoonya_broker(tool_input=test_input, context=mock_context)

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["user_id"], "test_uid")
        self.assertEqual(response["username"], "Test User")
        self.assertIn("WebSocket started", response["message"])
        
        self.assertEqual(agent.shoonya_user_token, "mock_token_xyz")
        self.assertEqual(agent.shoonya_user_id, "test_uid")
        self.assertEqual(agent.shoonya_username, "Test User")
        self.assertTrue(agent.websocket_connected)

        mock_api_instance.login.assert_called_once_with(
            userid=test_input.user_id,
            password=test_input.password,
            twoFA=test_input.two_fa_token,
            vc=test_input.vendor_code,
            api_secret=test_input.api_secret,
            imei=test_input.imei
        )
        mock_api_instance.start_websocket.assert_called_once_with(
            order_update_callback=agent._on_order_update_feed,
            subscribe_callback=agent._on_market_data_feed,
            socket_open_callback=agent._on_websocket_open,
            socket_close_callback=agent._on_websocket_close
        )

    @patch('shoonya_mcp_agent.agent.ShoonyaApiPy')
    async def test_connect_shoonya_broker_login_failure(self, MockShoonyaApiPyClass):
        mock_api_instance = MockShoonyaApiPyClass.return_value
        mock_api_instance.login.return_value = {"stat": "Not_Ok", "emsg": "Invalid login credentials"}

        agent = ShoonyaMCPAgent()
        # agent.shoonya_api = mock_api_instance # Not strictly needed due to class patch

        test_input = self._get_default_connect_input()
        mock_context = MagicMock(spec=ToolContext)

        response = await agent.connect_shoonya_broker(tool_input=test_input, context=mock_context)

        self.assertEqual(response["status"], "error")
        self.assertIn("Invalid login credentials", response["message"])
        
        self.assertIsNone(agent.shoonya_user_token)
        self.assertIsNone(agent.shoonya_user_id)
        self.assertFalse(agent.websocket_connected)
        mock_api_instance.start_websocket.assert_not_called()

    @patch('shoonya_mcp_agent.agent.ShoonyaApiPy')
    async def test_connect_shoonya_broker_login_exception(self, MockShoonyaApiPyClass):
        mock_api_instance = MockShoonyaApiPyClass.return_value
        mock_api_instance.login.side_effect = Exception("Network Error")

        agent = ShoonyaMCPAgent()
        test_input = self._get_default_connect_input()
        mock_context = MagicMock(spec=ToolContext)

        response = await agent.connect_shoonya_broker(tool_input=test_input, context=mock_context)

        self.assertEqual(response["status"], "error")
        self.assertIn("Network Error", response["message"])
        self.assertIsNone(agent.shoonya_user_token)
        self.assertFalse(agent.websocket_connected)
        mock_api_instance.start_websocket.assert_not_called()

    @patch('shoonya_mcp_agent.agent.ShoonyaApiPy')
    async def test_connect_shoonya_broker_websocket_failure_no_open_callback(self, MockShoonyaApiPyClass):
        mock_api_instance = MockShoonyaApiPyClass.return_value
        mock_api_instance.login.return_value = {
            "stat": "Ok", "susertoken": "mock_token_xyz", "uid": "test_uid", "uname": "Test User"
        }
        
        # Mock start_websocket to NOT call the _on_websocket_open callback
        mock_api_instance.start_websocket = MagicMock() # No side effect means callbacks aren't called

        agent = ShoonyaMCPAgent()
        test_input = self._get_default_connect_input()
        mock_context = MagicMock(spec=ToolContext)

        response = await agent.connect_shoonya_broker(tool_input=test_input, context=mock_context)
        
        self.assertEqual(response["status"], "error")
        self.assertIn("WebSocket connection failed to open", response["message"])
        self.assertIsNone(agent.shoonya_user_token) # Token should be reset if WS fails
        self.assertFalse(agent.websocket_connected)
        mock_api_instance.start_websocket.assert_called_once() # It was called

    @patch('shoonya_mcp_agent.agent.ShoonyaApiPy')
    async def test_connect_shoonya_broker_websocket_startup_exception(self, MockShoonyaApiPyClass):
        mock_api_instance = MockShoonyaApiPyClass.return_value
        mock_api_instance.login.return_value = {
            "stat": "Ok", "susertoken": "mock_token_xyz", "uid": "test_uid", "uname": "Test User"
        }
        
        mock_api_instance.start_websocket = MagicMock(side_effect=Exception("WebSocket Internal Error"))

        agent = ShoonyaMCPAgent()
        test_input = self._get_default_connect_input()
        mock_context = MagicMock(spec=ToolContext)

        response = await agent.connect_shoonya_broker(tool_input=test_input, context=mock_context)
        
        self.assertEqual(response["status"], "error")
        self.assertIn("WebSocket startup failed after login: WebSocket Internal Error", response["message"])
        self.assertIsNone(agent.shoonya_user_token)
        self.assertFalse(agent.websocket_connected)
        mock_api_instance.start_websocket.assert_called_once()

    @patch('shoonya_mcp_agent.agent.ShoonyaApiPy')
    async def test_connect_shoonya_broker_already_connected(self, MockShoonyaApiPyClass):
        mock_api_instance = MockShoonyaApiPyClass.return_value
        
        agent = ShoonyaMCPAgent()
        # Pre-set agent state to simulate already connected
        agent.shoonya_user_token = "existing_token"
        agent.shoonya_user_id = "existing_uid"
        agent.shoonya_username = "Existing User"
        agent.websocket_connected = True
        
        test_input = self._get_default_connect_input()
        mock_context = MagicMock(spec=ToolContext)

        response = await agent.connect_shoonya_broker(tool_input=test_input, context=mock_context)

        self.assertEqual(response["status"], "success")
        self.assertIn("Already connected to Shoonya as Existing User. WebSocket active.", response["message"])
        self.assertEqual(response["user_id"], "existing_uid")
        
        # Ensure login and start_websocket were not called again
        mock_api_instance.login.assert_not_called()
        mock_api_instance.start_websocket.assert_not_called()


if __name__ == '__main__':
    # This is to ensure that logging from the agent module is visible during tests
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    unittest.main()


class TestLiveMarketDataResource(unittest.IsolatedAsyncioTestCase):

    async def test_initialize_instrument(self):
        resource = LiveMarketDataResource()
        resource.notify_update = MagicMock(return_value=None) # Mock the async notify_update

        await resource.initialize_instrument("NSE|22")
        
        self.assertIn("NSE|22", resource._data)
        instrument_data = resource._data["NSE|22"]
        self.assertIsInstance(instrument_data, ShoonyaTickData)
        self.assertEqual(instrument_data.exchange, "NSE")
        self.assertEqual(instrument_data.token, "22")
        self.assertIsNone(instrument_data.last_traded_price) # Initialized fields should be None or default
        
        resource.notify_update.assert_called_once()
        # Check what initialize_instrument sends in notify_update
        expected_initial_data_notif = {'NSE|22': ShoonyaTickData(exchange='NSE', token='22').model_dump(by_alias=True, exclude_none=True)}
        resource.notify_update.assert_called_with(expected_initial_data_notif)


    async def test_update_tick_new_instrument(self):
        resource = LiveMarketDataResource()
        resource.notify_update = MagicMock(return_value=None)
        
        raw_tick_data = {"e": "NSE", "tk": "22", "lp": 123.45, "v": 1000, "t": "tf", "ft": "12:30:00"}
        
        await resource.update_tick("NSE|22", raw_tick_data)
        
        self.assertIn("NSE|22", resource._data)
        stored_data = resource._data["NSE|22"]
        self.assertIsInstance(stored_data, ShoonyaTickData)
        self.assertEqual(stored_data.exchange, "NSE")
        self.assertEqual(stored_data.token, "22")
        self.assertEqual(stored_data.last_traded_price, 123.45)
        self.assertEqual(stored_data.volume, 1000)
        self.assertEqual(stored_data.feed_timestamp, "12:30:00")
        self.assertIsNotNone(stored_data.mcp_received_timestamp)
        
        resource.notify_update.assert_called_once()
        # Verify the content of the notification
        # Pydantic model_dump converts to dict with original field names if by_alias=False (default)
        # or with alias names if by_alias=True
        expected_notification_data = ShoonyaTickData.parse_obj(raw_tick_data).model_dump(by_alias=True, exclude_none=True)
        # update_tick adds mcp_received_timestamp AFTER parsing, so we can't directly compare model_dump
        # We need to check the call argument structure
        call_args = resource.notify_update.call_args[0][0] # Gets the first positional argument of the call
        self.assertIn("NSE|22", call_args)
        self.assertEqual(call_args["NSE|22"]["lp"], 123.45)


    async def test_update_tick_existing_instrument(self):
        resource = LiveMarketDataResource()
        resource.notify_update = MagicMock(return_value=None)
        
        initial_tick = {"e": "NSE", "tk": "22", "lp": 100.0, "v": 500, "t": "tf"}
        await resource.update_tick("NSE|22", initial_tick)
        
        resource.notify_update.reset_mock() # Reset mock for the second call
        
        updated_tick = {"e": "NSE", "tk": "22", "lp": 101.5, "v": 600, "t": "tf"}
        await resource.update_tick("NSE|22", updated_tick)
        
        self.assertIn("NSE|22", resource._data)
        stored_data = resource._data["NSE|22"]
        self.assertEqual(stored_data.last_traded_price, 101.5)
        self.assertEqual(stored_data.volume, 600)
        
        resource.notify_update.assert_called_once()
        call_args = resource.notify_update.call_args[0][0]
        self.assertEqual(call_args["NSE|22"]["lp"], 101.5)


    async def test_update_tick_ignore_non_data_ticks(self):
        resource = LiveMarketDataResource()
        resource.notify_update = MagicMock(return_value=None)
        
        # 'tk' is an ack, not a data tick 'tf' or 'df'
        ack_tick_data = {"e": "NSE", "tk": "22", "t": "tk"} 
        
        await resource.update_tick("NSE|22", ack_tick_data)
        
        self.assertNotIn("NSE|22", resource._data) # Should not add if it's not a data tick
        resource.notify_update.assert_not_called()

        # Test with an existing instrument, it should not be updated by a non-data tick
        data_tick = {"e": "NSE", "tk": "22", "lp": 100.0, "t": "tf"}
        await resource.update_tick("NSE|22", data_tick)
        resource.notify_update.reset_mock()

        await resource.update_tick("NSE|22", ack_tick_data)
        self.assertEqual(resource._data["NSE|22"].last_traded_price, 100.0) # Should remain unchanged
        resource.notify_update.assert_not_called()


    async def test_remove_instrument(self):
        resource = LiveMarketDataResource()
        resource.notify_update = MagicMock(return_value=None)
        
        initial_tick = {"e": "NSE", "tk": "22", "lp": 100.0, "t": "tf"}
        await resource.update_tick("NSE|22", initial_tick)
        self.assertIn("NSE|22", resource._data)
        
        resource.notify_update.reset_mock() # Reset before the call we're testing
        
        await resource.remove_instrument("NSE|22")
        
        self.assertNotIn("NSE|22", resource._data)
        resource.notify_update.assert_called_once_with({"NSE|22": None})


    async def test_get_instrument_data(self):
        resource = LiveMarketDataResource()
        initial_tick_raw = {"e": "NSE", "tk": "22", "lp": 100.0, "t": "tf"}
        await resource.update_tick("NSE|22", initial_tick_raw)
        
        retrieved_data = await resource.get_instrument_data("NSE|22")
        self.assertIsInstance(retrieved_data, ShoonyaTickData)
        self.assertEqual(retrieved_data.last_traded_price, 100.0)
        
        non_existent_data = await resource.get_instrument_data("NSE|NONEXISTENT")
        self.assertIsNone(non_existent_data)


    async def test_get_all_data(self):
        resource = LiveMarketDataResource()
        tick1_raw = {"e": "NSE", "tk": "22", "lp": 100.0, "t": "tf"}
        tick2_raw = {"e": "NFO", "tk": "12345", "lp": 50.5, "t": "tf"}
        
        await resource.update_tick("NSE|22", tick1_raw)
        await resource.update_tick("NFO|12345", tick2_raw)
        
        all_data = await resource.get_all_data()
        
        self.assertIsInstance(all_data, dict)
        self.assertIn("NSE|22", all_data)
        self.assertIn("NFO|12345", all_data)
        self.assertEqual(all_data["NSE|22"].last_traded_price, 100.0)
        self.assertEqual(all_data["NFO|12345"].last_traded_price, 50.5)
        
        # Test that it's a copy
        all_data["NSE|22"].last_traded_price = 200.0
        self.assertEqual(resource._data["NSE|22"].last_traded_price, 100.0) # Original should be unchanged


class TestShoonyaMCPAgentPlaceOrder(unittest.IsolatedAsyncioTestCase):

    async def _create_agent_with_mocked_shoonya(self, is_connected=True):
        # This context manager ensures the patch is active only for the duration of the test method
        # that calls this helper. If we want it per-test-class, we'd use patch.object or class decorator.
        # For this helper, we'll assume the test method using it will manage the patch context.
        # The patch should be applied in the test method itself.
        
        mock_shoonya_api_instance = MagicMock(spec=ShoonyaApiPy) # Use spec for better mocking
        
        # Temporarily patch the __init__ of ShoonyaMCPAgent or its shoonya_api attribute for this instance
        # This is tricky because ShoonyaApiPy is instantiated in ShoonyaMCPAgent's __init__
        # A cleaner way is to allow injecting the api_instance or patching at class level for tests.
        # For now, let's assume we can replace it after instantiation for the test.
        
        agent = ShoonyaMCPAgent()
        agent.shoonya_api = mock_shoonya_api_instance # Replace with mock

        if is_connected:
            agent.shoonya_user_token = "mock_test_token"
            agent.shoonya_user_id = "test_user_id_for_actid"
            agent.shoonya_username = "Test User Connected"
            agent.websocket_connected = True # Assuming WebSocket is also connected for place_order tests
        else:
            agent.shoonya_user_token = None
            agent.shoonya_user_id = None
            agent.shoonya_username = None
            agent.websocket_connected = False
            
        return agent, mock_shoonya_api_instance

    def _get_default_place_order_input(self) -> PlaceOrderInput:
        return PlaceOrderInput(
            buy_or_sell='B', # trantype
            product_type='I', # prd
            exchange='NSE',   # exch
            tradingsymbol='INFY-EQ', # tsym
            quantity=10, # qty
            price_type='LMT', # prctyp
            price=1500.00, # prc
            # discloseqty, trigger_price, retention, amo, remarks can use defaults or be specified
        )

    @patch('shoonya_mcp_agent.agent.ShoonyaApiPy') # Patch at method level
    async def test_place_order_success(self, MockShoonyaApiPyClass):
        # MockShoonyaApiPyClass is the mocked class. We need to configure its return_value (the instance)
        mock_shoonya_api_instance = MockShoonyaApiPyClass.return_value
        
        agent = ShoonyaMCPAgent() # This will now use the mocked ShoonyaApiPy instance from the patch
        # Simulate successful connection
        agent.shoonya_user_token = "mock_test_token"
        agent.shoonya_user_id = "test_user_id_for_actid"
        agent.shoonya_username = "Test User Connected"
        agent.websocket_connected = True

        mock_shoonya_api_instance.place_order.return_value = {
            "stat": "Ok", 
            "norenordno": "123456789", 
            "result": "Order placed successfully"
        }
        
        test_input = self._get_default_place_order_input()
        mock_context = MagicMock(spec=ToolContext)
        
        response = await agent.place_order(tool_input=test_input, context=mock_context)
        
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["order_id"], "123456789")
        self.assertEqual(response["message"], "Order placed successfully")
        
        expected_call_args = test_input.model_dump(by_alias=True, exclude_none=True)
        expected_call_args['actid'] = agent.shoonya_user_id # Add actid
        mock_shoonya_api_instance.place_order.assert_called_once_with(**expected_call_args)

    @patch('shoonya_mcp_agent.agent.ShoonyaApiPy')
    async def test_place_order_shoonya_api_error(self, MockShoonyaApiPyClass):
        mock_shoonya_api_instance = MockShoonyaApiPyClass.return_value
        agent = ShoonyaMCPAgent()
        agent.shoonya_user_token = "mock_test_token"
        agent.shoonya_user_id = "test_user_id_for_actid"
        # No need to set username/websocket_connected for this test focus

        mock_shoonya_api_instance.place_order.return_value = {
            "stat": "Not_Ok", 
            "emsg": "Insufficient funds for order."
        }
        
        test_input = self._get_default_place_order_input()
        mock_context = MagicMock(spec=ToolContext)
        
        response = await agent.place_order(tool_input=test_input, context=mock_context)
        
        self.assertEqual(response["status"], "error")
        self.assertIn("Insufficient funds for order.", response["message"])
        self.assertIsNone(response.get("order_id"))
        mock_shoonya_api_instance.place_order.assert_called_once()

    @patch('shoonya_mcp_agent.agent.ShoonyaApiPy')
    async def test_place_order_exception_in_api_call(self, MockShoonyaApiPyClass):
        mock_shoonya_api_instance = MockShoonyaApiPyClass.return_value
        agent = ShoonyaMCPAgent()
        agent.shoonya_user_token = "mock_test_token"
        agent.shoonya_user_id = "test_user_id_for_actid"

        mock_shoonya_api_instance.place_order.side_effect = Exception("Network timeout")
        
        test_input = self._get_default_place_order_input()
        mock_context = MagicMock(spec=ToolContext)
        
        response = await agent.place_order(tool_input=test_input, context=mock_context)
        
        self.assertEqual(response["status"], "error")
        self.assertIn("An exception occurred: Network timeout", response["message"])
        self.assertIsNone(response.get("order_id"))
        mock_shoonya_api_instance.place_order.assert_called_once()

    @patch('shoonya_mcp_agent.agent.ShoonyaApiPy') # Patch here so agent created below uses the mock
    async def test_place_order_not_connected(self, MockShoonyaApiPyClass):
        # The helper is not used here to ensure the mock is applied correctly by the decorator
        mock_shoonya_api_instance = MockShoonyaApiPyClass.return_value 
        agent = ShoonyaMCPAgent() 
        # Ensure agent is NOT connected
        agent.shoonya_user_token = None
        agent.shoonya_user_id = None
        
        test_input = self._get_default_place_order_input()
        mock_context = MagicMock(spec=ToolContext)
        
        response = await agent.place_order(tool_input=test_input, context=mock_context)
        
        self.assertEqual(response["status"], "error")
        self.assertIn("Not connected to Shoonya. Please call 'connect_shoonya_broker' first.", response["message"])
        mock_shoonya_api_instance.place_order.assert_not_called()
