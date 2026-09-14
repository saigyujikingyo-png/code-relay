import unittest

from code_relay.server import Server


class ProtocolTests(unittest.TestCase):
    def test_initialize_negotiates_and_notifications_do_not_reply(self):
        server = Server()
        self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        answer = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(answer["result"]["protocolVersion"], "2025-06-18")

    def test_rejects_invalid_shape_and_preinitialize_tools(self):
        server = Server()
        for value in [[], None, {"method": "tools/list"}, {"jsonrpc": "2.0", "id": [], "method": "ping"}]:
            self.assertEqual(server.handle(value)["error"]["code"], -32600)
        self.assertEqual(server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["error"]["code"], -32000)

    def test_bad_params_are_protocol_errors(self):
        server = Server()
        self.assertEqual(server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": []})["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
