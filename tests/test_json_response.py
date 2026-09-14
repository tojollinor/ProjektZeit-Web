import io
import json
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
import app


class JsonResponseTest(unittest.TestCase):
    def test_serialization_failure_returns_parseable_error_before_headers(self):
        handler=SimpleNamespace(send_response=Mock(),send_header=Mock(),end_headers=Mock(),wfile=io.BytesIO())
        with patch('logging.exception'):
            app.App.send_json(handler,200,{'value':Decimal(1)})
        handler.send_response.assert_called_once_with(500)
        handler.send_header.assert_any_call('Content-Type','application/json; charset=utf-8')
        self.assertEqual(json.loads(handler.wfile.getvalue())['action_state'],'uncertain')
