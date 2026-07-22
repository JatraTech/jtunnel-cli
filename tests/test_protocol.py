from jtunnel.protocol import MAX_WS_MESSAGE_SIZE, REQUEST_TIMEOUT_SECONDS


def test_request_timeout_seconds():
    assert REQUEST_TIMEOUT_SECONDS == 300


def test_max_ws_message_size():
    assert MAX_WS_MESSAGE_SIZE == 32 * 1024 * 1024
