import collections
import random
from concurrent import futures
import time
import grpc
import sys
import os
import logging 

sys.path.append('./protos')
import protos.client_pb2 as client_pb2
import protos.client_pb2_grpc as client_pb2_grpc

sys.path.append('./logs')
from log_formatter import format_log

class ClientServicer(client_pb2_grpc.ClientServicer):
    def __init__(self, id, message_q):
        log_folder = '../logs'
        os.makedirs(log_folder, exist_ok=True)

        self.id = id
        log_file_name = f"client_{id}_log.txt"
        self.log_file_path = os.path.join(log_folder, log_file_name)
        self.log_file = open(self.log_file_path, 'a')

        self.message_q = message_q

    def __del__(self):
        self.log_file.close()

    def SendMessage(self, request_iterator, context):
        '''
            Receive messages from a client
        '''

        for request in request_iterator:
            sender_id = request.sender_id
            logical_time = request.logical_time
            physical_time = request.physical_time

            logging.info(f"Message Received from client {sender_id}")

            try:
                # log = format_log("receive", sender_id, self.id, logical_time, physical_time)
                # self.log_file.write(log)
                message = {
                    "sender_id": sender_id,
                    "logical_time": logical_time,
                    "physical_time": physical_time
                }
                self.message_q.append(message)

                response = client_pb2.Response(success=True)
            except Exception as e:
                response = client_pb2.Response(success=False)

                logging.info(f"Error: {e}")
                self.log_file.write(f"Error: {e}\n")

            yield response

        


    