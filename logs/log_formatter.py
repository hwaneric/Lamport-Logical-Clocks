def format_log(event, sender_id, recipient_id, logical_time, physical_time, message_queue_length):
    '''
        Format log message
    '''
    
    match event:
        case "send":
            log_message = f"EVENT: Send Msg | RECIPIENT: {recipient_id} | LOGICAL TIME: {logical_time} | PHYSICAL TIME: {physical_time}, MESSAGE QUEUE LENGTH: {message_queue_length}\n"
        case "receive":
            log_message = f"EVENT: Receive Msg | SENDER: {sender_id} | LOGICAL TIME: {logical_time} | PHYSICAL TIME: {physical_time}, MESSAGE QUEUE LENGTH: {message_queue_length}\n"
        case "internal":
            log_message = f"EVENT: Internal Event | LOGICAL TIME: {logical_time} | PHYSICAL TIME: {physical_time}, MESSAGE QUEUE LENGTH: {message_queue_length}\n"
        case _:
            raise ValueError(f"Invalid event: {event}")
    return log_message