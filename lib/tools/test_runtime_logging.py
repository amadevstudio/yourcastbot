import logging
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from lib.tools.runtime_logging import RuntimeHandler, install_runtime_logging


class LoggingTest(unittest.TestCase):
    def test_bot_token_never_reaches_a_log_line(self):
        import io
        from contextlib import redirect_stdout
        from lib.tools.logger import Logger, redact
        token = "1234567890:" + "AAFakeTokenForTestsOnly_abcdefghij-XYZ"  # made up
        out = io.StringIO()
        with patch("config.server", False), redirect_stdout(out):
            Logger(file="test").warn("Max retries exceeded with url: /bot%s/editMessageText" % token)
        self.assertNotIn(token.split(":")[1], out.getvalue())
        self.assertIn("/bot<bot token>/editMessageText", out.getvalue())
        self.assertEqual(redact("chat 5550001, 12:30"), "chat 5550001, 12:30")  # ids and times stay

    def test_library_error_and_warning_become_diagnostic_lines(self):
        target = Mock()
        handler = RuntimeHandler(target)
        try:
            raise RuntimeError('worker failed')
        except RuntimeError:
            record = logging.LogRecord('telethon.test', logging.ERROR, __file__, 1,
                                       'upload failed', (), sys.exc_info())
        handler.emit(record)
        args = target.custom_err.call_args.args
        self.assertEqual(args[0], 'telethon.test:')
        self.assertIn('worker failed', args[1])
        self.assertIn('test_runtime_logging.py', args[1])
        self.assertNotIn('\n', args[1])
        handler.emit(logging.LogRecord('feed', logging.WARNING, __file__, 1, 'retry %s', (3,), None))
        target.warn.assert_called_once_with('feed:', 'retry 3')

    def test_install_is_idempotent_and_captures_uncaught_errors(self):
        import threading
        target = Mock()
        with patch.object(logging.getLogger(), 'handlers', []), \
                patch('lib.tools.runtime_logging.Logger', return_value=target) as factory, \
                patch.object(sys, 'excepthook') as previous, patch.object(threading, 'excepthook'):
            install_runtime_logging('jobs')
            install_runtime_logging('jobs')
            factory.assert_called_once_with(file='runtime_jobs')
            try:
                raise RuntimeError('uncaught test')
            except RuntimeError:
                sys.excepthook(*sys.exc_info())
            self.assertIn('uncaught test', target.custom_err.call_args.args[1])
            previous.assert_called_once()


if __name__ == '__main__':
    unittest.main()
