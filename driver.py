import time
from clients.client import Client
import multiprocessing
import logging

def run_client(id):
    configure_logging()
    client = Client(id)
    threads = []

    # Connect to the other 2 clients
    for i in range(1, 4):
        if i != id:
            thread = client.connect(i)
            threads.append(thread)
    
    for i in range(1, 4):
        if i != id:
            client._send_message(i, synchronous=True)

    start_time = time.time()
    while time.time() - start_time < 5:
        client._process_event()
        time.sleep(1 / client.clock_rate)

    client.cleanup()

# Function to configure logging for each process
def configure_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  

    # Create a file handler to write logs to a file
    file_handler = logging.FileHandler('./logs/debugging_logs.log')
    file_handler.setLevel(logging.DEBUG)

     # Clear the log file by opening it in write mode
    with open('./logs/debugging_logs.log', 'w'):
        pass

    # Create a logging format
    formatter = logging.Formatter('%(asctime)s - %(processName)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(file_handler)

if __name__ == '__main__':
    configure_logging()
    logging.info("Starting the processes")

    processes = []

    for id in range(1, 4):
        p = multiprocessing.Process(target=run_client, args=(id,))
        processes.append(p)
        p.start()

    # Wait for all processes
    for p in processes:
        p.join()
    
   