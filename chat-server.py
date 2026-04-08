import socket
import threading
from datetime import datetime
import time

HOST = ""
PORT = 8080

clients = {}
clients_lock = threading.Lock()

history = []
MAX_HISTORY = 20

SPAM_LIMIT = 5
SPAM_WINDOW = 1

last_messages = {}

def timestamp():
    return datetime.now().strftime("%H:%M:%S")

def log(msg):
    print(msg)

    with open("chat.log","a",encoding="utf-8") as f:
        f.write(msg+"\n")

def broadcast(message, sender_socket=None):

    with clients_lock:

        for client in list(clients.keys()):

            if client != sender_socket:

                try:
                    client.send(message.encode())

                except:
                    client.close()
                    del clients[client]

def send_history(sock):

    if not history:
        return

    sock.send("[Server] Last messages:\n".encode())

    for msg in history:
        sock.send((msg+"\n").encode())

def add_history(msg):

    history.append(msg)

    if len(history) > MAX_HISTORY:
        history.pop(0)

def send_user_list(sock):

    with clients_lock:
        users = ", ".join(clients.values())

    sock.send(f"[Server] Online users: {users}\n".encode())

def private_message(sender_sock,target,msg):

    with clients_lock:

        sender = clients.get(sender_sock)

        for sock,name in clients.items():

            if name == target:

                time_str = timestamp()

                formatted = f"[PM] {sender} -> {target}: {msg} [{time_str}]"

                log(formatted)

                sock.send((formatted+"\n").encode())

                return

    sender_sock.send("[Server] User not found\n".encode())

def send_help(sock):

    help_text = """

Commands:

/help
show help

/users
show online users

/msg USER MESSAGE
send private message

/time on
show timestamps

/time off
hide timestamps

/quit
exit chat

"""

    sock.send(help_text.encode())

def check_spam(sock):

    now = time.time()

    if sock not in last_messages:
        last_messages[sock] = []

    last_messages[sock].append(now)

    last_messages[sock] = [
        t for t in last_messages[sock]
        if now - t < SPAM_WINDOW
    ]

    if len(last_messages[sock]) > SPAM_LIMIT:
        return True

    return False

def handle_client(sock,addr):

    sock.send("Enter your username: ".encode())

    username = sock.recv(1024).decode().strip()

    with clients_lock:
        clients[sock] = username

    log(f"[+] {username} connected from {addr}")

    broadcast(f"[Server] {username} joined the chat\n")

    send_history(sock)

    while True:

        try:

            data = sock.recv(1024)

            if not data:
                break

            message = data.decode().strip()

            if check_spam(sock):
                sock.send("[Server] Slow down!\n".encode())
                continue

            if message.startswith("/"):

                parts = message.split(" ",2)
                command = parts[0]

                if command == "/users":

                    send_user_list(sock)

                elif command == "/msg" and len(parts) >=3:

                    private_message(sock,parts[1],parts[2])

                elif command == "/help":

                    send_help(sock)

                elif command == "/quit":

                    break

                else:

                    sock.send("[Server] Unknown command\n".encode())

            else:

                time_str = timestamp()

                user = clients.get(sock)

                formatted = f"{user}: {message} [{time_str}]"

                log(formatted)

                add_history(formatted)

                broadcast(formatted+"\n",sock)

        except:
            break

    with clients_lock:

        user = clients.get(sock,"unknown")

        if sock in clients:
            del clients[sock]

    log(f"[-] {user} disconnected")

    broadcast(f"[Server] {user} left the chat\n")

    sock.close()

def start_server():

    server = socket.socket(socket.AF_INET,socket.SOCK_STREAM)

    server.bind((HOST,PORT))

    server.listen(5)

    print(f"Server running on port {PORT}")

    while True:

        client,addr = server.accept()

        thread = threading.Thread(
            target=handle_client,
            args=(client,addr)
        )

        thread.start()

if __name__ == "__main__":
    start_server()
