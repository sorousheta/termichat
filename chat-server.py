import socket
import threading
from datetime import datetime
import time

HOST = ""
PORT = 12345

clients = {}
clients_lock = threading.Lock()

history = []
history_lock = threading.Lock()
MAX_HISTORY = 20

SPAM_LIMIT = 5
SPAM_WINDOW = 1

last_messages = {}

log_lock = threading.Lock()


def timestamp():
    return datetime.now().strftime("%H:%M:%S")


def log(msg):
    print(msg)
    with log_lock:
        with open("chat.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")


def broadcast(message, sender_socket=None):
    with clients_lock:
        dead = []
        for client in clients.keys():
            if client != sender_socket:
                try:
                    client.send((message).encode())
                except Exception:
                    dead.append(client)

        for d in dead:
            try:
                d.close()
            except:
                pass
            clients.pop(d, None)


def send_history(sock):
    with history_lock:
        if not history:
            return

        try:
            sock.send("[Server] Last messages:\n".encode())
            for msg in history:
                sock.send((msg + "\n").encode())
        except:
            pass


def add_history(msg):
    with history_lock:
        history.append(msg)
        if len(history) > MAX_HISTORY:
            history.pop(0)


def send_user_list(sock):
    with clients_lock:
        users = ", ".join(clients.values())

    sock.send(f"[Server] Online users: {users}\n".encode())


def private_message(sender_sock, target, msg):
    with clients_lock:
        sender = clients.get(sender_sock)

        for sock, name in clients.items():
            if name == target:

                time_str = timestamp()
                formatted = f"[PM] {sender} -> {target}: {msg} [{time_str}]"

                log(formatted)

                try:
                    sock.send((formatted + "\n").encode())
                    sender_sock.send((formatted + "\n").encode())
                except:
                    pass
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

    return len(last_messages[sock]) > SPAM_LIMIT


def handle_client(sock, addr):

    try:
        sock.send("Enter your username: ".encode())
        username = sock.recv(1024).decode().strip()
    except:
        sock.close()
        return

    if not username:
        sock.close()
        return

    with clients_lock:

        if username in clients.values():
            sock.send("[Server] Username already taken\n".encode())
            sock.close()
            return

        clients[sock] = username

    log(f"[+] {username} connected from {addr}")

    broadcast(f"[Server] {username} joined the chat\n", sock)

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

                parts = message.split(" ", 2)
                command = parts[0]

                if command == "/users":
                    send_user_list(sock)

                elif command == "/msg" and len(parts) >= 3:
                    private_message(sock, parts[1], parts[2])

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

                broadcast(formatted + "\n", sock)

        except Exception:
            break

    with clients_lock:
        user = clients.pop(sock, "unknown")

    last_messages.pop(sock, None)

    log(f"[-] {user} disconnected")

    broadcast(f"[Server] {user} left the chat\n", sock)

    try:
        sock.close()
    except:
        pass


def start_server():

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server.bind((HOST, PORT))
    server.listen(10)

    print(f"Server running on port {PORT}")

    while True:

        client, addr = server.accept()

        thread = threading.Thread(
            target=handle_client,
            args=(client, addr),
            daemon=True
        )

        thread.start()


if __name__ == "__main__":
    start_server()
