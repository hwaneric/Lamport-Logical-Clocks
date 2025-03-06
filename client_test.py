import pytest
import grpc
from unittest import mock
import threading
import time
from clients.client import Client
from clients.client_servicer import ClientServicer
import protos.client_pb2 as client_pb2
from driver import configure_logging
import logging

@pytest.fixture
def client():
    with mock.patch.object(Client, '_serve', return_value=None):
        client = Client(id=1)
        yield client
        client.cleanup()

def test_connect_success(client):
    with mock.patch('grpc.insecure_channel') as mock_insecure_channel, \
         mock.patch('grpc.channel_ready_future') as mock_channel_ready_future, \
         mock.patch('threading.Thread') as mock_thread:
        
        mock_channel_instance = mock.Mock()
        mock_insecure_channel.return_value = mock_channel_instance
        mock_channel_ready_future.return_value.result.return_value = None

        client.connect(2)

        mock_insecure_channel.assert_called_once_with(f"{client._get_address(2)[0]}:{client._get_address(2)[1]}")
        mock_channel_ready_future.assert_called_once_with(mock_channel_instance)
        mock_thread.assert_called_once_with(target=client._run_messaging_thread, args=(2,), daemon=True)
        assert 2 in client.stubs
        assert 2 in client.channels

def test_connect_retry(client):
    with mock.patch('grpc.insecure_channel') as mock_insecure_channel, \
         mock.patch('grpc.channel_ready_future') as mock_channel_ready_future, \
         mock.patch('threading.Thread') as mock_thread, \
         mock.patch('time.sleep', return_value=None) as mock_sleep:
        
        mock_channel_instance = mock.Mock()
        mock_insecure_channel.return_value = mock_channel_instance
        mock_channel_ready_future.return_value.result.side_effect = grpc.FutureTimeoutError()

        with pytest.raises(ConnectionError):
            client.connect(2)

        assert mock_insecure_channel.call_count == 10
        assert mock_channel_ready_future.call_count == 10
        assert mock_sleep.call_count == 10
        assert 2 not in client.stubs
        assert 2 not in client.channels
        mock_thread.assert_not_called()

def test_generate_messages(client):
    recipient_id = 2
    message = {
        "sender_id": client.id,
        "message": f"Message from client {client.id}",
        "logical_time": client.clock_count,
        "physical_time": int(time.time())
    }
    client.messages_to_send[recipient_id].append(message)

    message_generator = client._generate_messages(recipient_id)
    generated_message = next(message_generator)

    assert generated_message.sender_id == message["sender_id"]
    assert generated_message.message == message["message"]
    assert generated_message.logical_time == message["logical_time"]
    assert generated_message.physical_time == message["physical_time"]

    client.stop_event.set()
    with pytest.raises(StopIteration):
        next(message_generator)

def test_run_messaging_thread(client):
    recipient_id = 2
    message = {
        "sender_id": client.id,
        "message": f"Message from client {client.id}",
        "logical_time": client.clock_count,
        "physical_time": int(time.time())
    }
    client.messages_to_send[recipient_id].append(message)

    mock_stub = mock.Mock()
    mock_channel = mock.Mock()
    client.stubs[recipient_id] = mock_stub
    client.channels[recipient_id] = mock_channel

    def mock_send_message(request_iterator):
        for request in request_iterator:
            yield client_pb2.Response()

    mock_stub.SendMessage.side_effect = mock_send_message

    messaging_thread = threading.Thread(target=client._run_messaging_thread, args=(recipient_id,), daemon=True)
    messaging_thread.start()

    time.sleep(1)

    client.stop_event.set()
    messaging_thread.join()

    mock_stub.SendMessage.assert_called_once()
    mock_channel.close.assert_called_once()

    assert client.stop_event.is_set()

    assert not client.messages_to_send[recipient_id]

def test_run_messaging_thread_unavailable(client):
    recipient_id = 2
    client.stubs[recipient_id] = mock.Mock()
    client.channels[recipient_id] = mock.Mock()

    class UnavailableRpcError(grpc.RpcError):
        def code(self):
            return grpc.StatusCode.UNAVAILABLE

    def mock_send_message(request_iterator):
        raise UnavailableRpcError()

    client.stubs[recipient_id].SendMessage.side_effect = mock_send_message

    messaging_thread = threading.Thread(target=client._run_messaging_thread, args=(recipient_id,), daemon=True)
    messaging_thread.start()

    time.sleep(1)

    client.stop_event.set()
    messaging_thread.join()

    client.stubs[recipient_id].SendMessage.assert_called_once()
    client.channels[recipient_id].close.assert_called_once()

def test_run_messaging_thread_other_error(client):
    recipient_id = 2
    client.stubs[recipient_id] = mock.Mock()
    client.channels[recipient_id] = mock.Mock()

    class InternalRpcError(grpc.RpcError):
        def code(self):
            return grpc.StatusCode.INTERNAL

    def mock_send_message(request_iterator):
        raise InternalRpcError()

    client.stubs[recipient_id].SendMessage.side_effect = mock_send_message

    messaging_thread = threading.Thread(target=client._run_messaging_thread, args=(recipient_id,), daemon=True)
    messaging_thread.start()

    time.sleep(1)

    client.stop_event.set()
    messaging_thread.join()

    client.stubs[recipient_id].SendMessage.assert_called_once()
    client.channels[recipient_id].close.assert_called_once()

def test_send_message(client):
    recipient_id = 2
    message = {
        "sender_id": client.id,
        "message": f"Message from client {client.id}",
        "logical_time": client.clock_count,
        "physical_time": int(time.time())
    }

    mock_channel = mock.Mock()
    client.stubs.clear()
    client.channels[recipient_id] = mock_channel

    with mock.patch.object(client, 'connect', return_value=None) as mock_connect:
        client._send_message(recipient_id)

        mock_connect.assert_called_once_with(recipient_id)

        assert client.messages_to_send[recipient_id]
        sent_message = client.messages_to_send[recipient_id].popleft()
        assert sent_message["sender_id"] == message["sender_id"]
        assert sent_message["message"] == message["message"]
        assert sent_message["logical_time"] == message["logical_time"]
        assert sent_message["physical_time"] == message["physical_time"]

@pytest.fixture
def client():
    with mock.patch.object(Client, '_serve', return_value=None):
        client = Client(id=1)
        yield client
        client.cleanup()

def test_process_event_receive(client):
    message = {
        "sender_id": 2,
        "message": "Test message",
        "logical_time": 5,
        "physical_time": int(time.time())
    }
    client.message_q.append(message)

    with mock.patch('log_formatter.format_log', return_value="Log message") as mock_log_formatter:
        with mock.patch.object(client, 'event_logger') as mock_event_logger:
            client._process_event()

            # Ensure the message was processed and the clock count was updated
            assert client.clock_count == 6
            assert not client.message_q

            # Ensure the log message was generated
            mock_log_formatter.assert_called_once_with(
                "receive",
                message["sender_id"],
                client.id,
                client.clock_count,
                mock.ANY,  # current_time
                1  # message_queue_length
            )
            mock_event_logger.info.assert_called_once_with("Log message")

def test_process_event_send(client):
    client.message_q.clear()
    client.clock_count = 0

    with mock.patch('random.randint', return_value=1), \
         mock.patch('log_formatter.format_log', return_value="Log message") as mock_log_formatter, \
         mock.patch.object(client, '_send_message') as mock_send_message, \
         mock.patch.object(client, 'event_logger') as mock_event_logger:
        
        client._process_event()

        # Ensure the message was sent and the clock count was updated
        assert client.clock_count == 1
        mock_send_message.assert_called_once_with((client.id % 3) + 1)

        mock_log_formatter.assert_called_once_with(
            "send",
            client.id,
            (client.id % 3) + 1,
            client.clock_count,
            mock.ANY,
            0
        )
        mock_event_logger.info.assert_called_once_with("Log message")

def test_process_event_internal(client):
    client.message_q.clear()
    client.clock_count = 0

    with mock.patch('random.randint', return_value=4), \
         mock.patch('log_formatter.format_log', return_value="Log message") as mock_log_formatter, \
         mock.patch.object(client, 'event_logger') as mock_event_logger:
        
        client._process_event()

        # Ensure the clock count was updated
        assert client.clock_count == 1

        # Ensure the log message was generated
        mock_log_formatter.assert_called_once_with(
            "internal",
            client.id,
            None,
            client.clock_count,
            mock.ANY,  # current_time
            0  # message_queue_length
        )
        mock_event_logger.info.assert_called_once_with("Log message")

def test_setup_logging(client):
    with mock.patch('logging.getLogger') as mock_get_logger, \
         mock.patch('logging.FileHandler') as mock_file_handler, \
         mock.patch('logging.Formatter') as mock_formatter:
        
        mock_logger = mock.Mock()
        mock_get_logger.return_value = mock_logger
        mock_file_handler_instance = mock.Mock()
        mock_file_handler.return_value = mock_file_handler_instance
        mock_formatter_instance = mock.Mock()
        mock_formatter.return_value = mock_formatter_instance

        client._setup_logging()

        mock_get_logger.assert_called_once_with(f"Client {client.id} Event Logger")
        mock_logger.setLevel.assert_called_once_with(logging.DEBUG)
        assert mock_logger.propagate is False

        mock_file_handler.assert_called_once_with(f"./logs/client_{client.id}_events.log")
        mock_file_handler_instance.setLevel.assert_called_once_with(logging.DEBUG)
        mock_file_handler_instance.setFormatter.assert_called_once_with(mock_formatter_instance)

        mock_formatter.assert_called_once_with('%(asctime)s - %(levelname)s - %(message)s')

        mock_logger.addHandler.assert_called_once_with(mock_file_handler_instance)

        mock_logger.info.assert_called_once_with(f"Clock rate for client {client.id}: {client.clock_rate} events per second")