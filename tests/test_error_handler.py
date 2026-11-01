import unittest
from types import SimpleNamespace
import main

class TelegramErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_unhandled_update_is_logged_and_consumed(self):
        error = RuntimeError("synthetic test failure")
        event = SimpleNamespace(exception=error)
        with self.assertLogs("peak-adventure", level="ERROR") as captured:
            handled = await main.handle_unhandled_error(event)
        self.assertTrue(handled)
        self.assertIn("RuntimeError", captured.output[0])
        self.assertNotIn("synthetic test failure", captured.output[0])

if __name__ == "__main__":
    unittest.main()
