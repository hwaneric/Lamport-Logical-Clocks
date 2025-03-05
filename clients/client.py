import collections
import random
from concurrent import futures
import threading
import time
import grpc
from clients.client_servicer import ClientServicer
import sys
import logging
from datetime import datetime

from dotenv import load_dotenv
import os

sys.path.append('./logs')
import log_formatter

sys.path.append('./protos')
import client_pb2
import client_pb2_grpc

# Create a server for each machine, and then connect to the servers of the other 2 machines to send machines 
class Client:
    def __init__(self, id):
        self.id = id
        self.clock_rate = random.randint(1, 6)   # Number of events per second, print this value
        self.clock_count = 0    # Logical clock count

        self.stubs = {}    # Stubs for connecting to other clients
        self.channels = {}  # Channels for connecting to other clients

        self.message_q = collections.deque()    # Messages received from other clients
        self.messages_to_send = collections.defaultdict(collections.deque) # Messages to send to other clients

        
        self.stop_event = threading.Event()  # Threading event that tells threads to gracefully exit
        self.threads = []   # Threads opened by the client

        self.server = None
        self._setup_logging()
        # Start the server
        self.serve(id, self.message_q)

    def _setup_logging(self):
        '''
            Setup logging for the client
        '''
        # Create a logging format
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Create a separate file handler for process_event logs
        self.event_logger = logging.getLogger(f"Client {self.id} Event Logger")
        self.event_logger.setLevel(logging.DEBUG)
        self.event_logger.propagate = False  # Disable propagation to avoid logging to other loggers

        event_file_handler = logging.FileHandler(f"./logs/client_{self.id}_events.log")
        event_file_handler.setLevel(logging.DEBUG)
        event_file_handler.setFormatter(formatter)

        self.event_logger.addHandler(event_file_handler)

        self.event_logger.info(f"Clock rate for client {self.id}: {self.clock_rate} events per second")

    def serve(self, id, message_q):
        '''
            Create new thread (to be non-blocking) that creates a server for the client
        '''
        server_thread = threading.Thread(target=self._serve, args=(id, message_q))
        server_thread.start()
        return server_thread
        
    def _serve(self, id, message_q):
        '''
            Spin up a server for the client
        '''
        HOST, PORT = self._get_address(id)

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        client_pb2_grpc.add_ClientServicer_to_server(ClientServicer(id, message_q), server)
        server.add_insecure_port(f"{HOST}:{PORT}")
        self.server = server
        logging.info(f"Starting server for client {id} at {HOST}:{PORT}")
        server.start()
        server.wait_for_termination()
        logging.info(f"Server for client {id} stopped")
    
    def connect(self, id):
        '''
            Connect to a client

            Returns the messaging thread, which should be joined by the main process
        '''
        HOST, PORT = self._get_address(id)
        
        max_retries = 10
        retry_delay = 2  # seconds

        # Attempt to connect to the server of client {id}
        for attempt in range(max_retries):
            try:
                channel = grpc.insecure_channel(f"{HOST}:{PORT}")
                grpc.channel_ready_future(channel).result(timeout=retry_delay)
                self.stubs[id] = client_pb2_grpc.ClientStub(channel)
                self.channels[id] = channel

                messaging_thread = threading.Thread(target=self._run_messaging_thread, args=(id,), daemon=True)
                messaging_thread.start()

                logging.info(f"Connected to client {id} at {HOST}:{PORT}")
                self.threads.append(messaging_thread)
                return
            
            except grpc.FutureTimeoutError:
                logging.info(f"Attempt {attempt + 1} to connect to client {id} at {HOST}:{PORT} failed. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)

        raise ConnectionError(f"Failed to connect to client {id} at {HOST}:{PORT} after {max_retries} attempts")

    def _generate_messages(self, recipient_id):
        '''
            Generate a message stream to send to a client
        '''
        while True:
            # Exit if stop event is set
            if self.stop_event.is_set():
                logging.info(f"Stopping messaging thread for client {recipient_id}")
                break
            
            # If there are messages to send, add them to the message stream
            if self.messages_to_send[recipient_id]:
                message = self.messages_to_send[recipient_id].popleft()
                yield client_pb2.Message(**message)
            else:
                # time.sleep(0.1)
                continue
        
    def _run_messaging_thread(self, recipient_id):
        '''
            Function that runs in thread for sending message to a client
            
            Automatically sends any messages that are added to the messages_to_send 
            queue to the recipient client
        '''

        stub = self.stubs[recipient_id]
        try:
            responses = stub.SendMessage(self._generate_messages(recipient_id))
            for response in responses:
                if self.stop_event.is_set():
                    break

        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                logging.info(f"Client {recipient_id} is unavailable. This is likely the result of graceful server shutdown and can be ignored.")
            else:
                logging.error(f"Error sending messages to client {recipient_id}: {e}")
        finally:
            channel = self.channels[recipient_id]
            channel.close()


    def _send_message(self, recipient_id, synchronous=False):
        '''
            Send a message to a client

            If synchronous argument is True, waits for the message to finish sending before returning
        '''

        if recipient_id not in self.stubs:
            self.connect(recipient_id)


        self.messages_to_send[recipient_id].append({
            "sender_id": self.id,
            "message": f"Message from client {self.id}",
            "logical_time": self.clock_count,
            "physical_time": int(time.time())
        })

        while self.messages_to_send[recipient_id] and synchronous:
            continue

    def _get_address(self, id):
        load_dotenv()
        match id:
            case 1:
                HOST = os.getenv("HOST_1")
                PORT = int(os.getenv("PORT_1"))
            case 2:
                HOST = os.getenv("HOST_2")
                PORT = int(os.getenv("PORT_2"))
            case 3:
                HOST = os.getenv("HOST_3")
                PORT = int(os.getenv("PORT_3"))
            case _:
                raise ValueError(f"Invalid client id: {id}")
        return HOST, PORT
    
    def _process_event(self):
        '''
            Process an event based on a random number.
            If there are no messages in the queue, generate a random number and:
            - If 1, send a message to one of the other machines.
            - If 2, send a message to the other machine.
            - If 3, send a message to both machines.
            - If other, treat as an internal event.
        '''
        message_queue_length = len(self.message_q)
        current_time = datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S.%f')[:-4]

        if self.message_q: 
            message = self.message_q.popleft()
            self.clock_count = max(self.clock_count, message['logical_time']) + 1
            log_message = log_formatter.format_log(
                "receive", 
                message['sender_id'], 
                self.id, self.clock_count, 
                current_time,
                message_queue_length
            )
            self.event_logger.info(log_message) 
        else:
            event_val = random.randint(1, 7)
            self.clock_count += 1

            if event_val == 1: 
                recipient_id = (self.id % 3) + 1
                self._send_message(recipient_id)
                log_message = log_formatter.format_log(
                    "send", 
                    self.id, 
                    recipient_id, 
                    self.clock_count, 
                    current_time, 
                    message_queue_length
                )
                self.event_logger.info(log_message) 
            elif event_val == 2: 
                recipient_id = ((self.id + 1) % 3) + 1
                self._send_message(recipient_id)
                log_message = log_formatter.format_log(
                    "send", 
                    self.id, 
                    recipient_id, 
                    self.clock_count, 
                    current_time,
                    message_queue_length
                )
                self.event_logger.info(log_message) 

            elif event_val == 3: 
                recipient_ids = [id for id in range(1, 4) if id != self.id]
                for recipient_id in recipient_ids:
                    self._send_message(recipient_id)
                log_message = log_formatter.format_log(
                    "send", 
                    self.id, 
                    f"{recipient_ids[0]} and {recipient_ids[1]}", 
                    self.clock_count, 
                    current_time, 
                    message_queue_length
                )
                self.event_logger.info(log_message) 
            else: 
                log_message = log_formatter.format_log(
                    "internal", 
                    self.id,   
                    None, 
                    self.clock_count,
                    current_time, 
                    message_queue_length
                )
                self.event_logger.info(log_message) 

    def cleanup(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join()

        if self.server:
            self.server.stop(0)

    def __del__(self):
        if self.server:
            self.server.stop(0)
            logging.info("Server stopped")
        logging.info("Closing client")