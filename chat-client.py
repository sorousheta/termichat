import socket
import threading
import sys

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 12345

show_timestamp = True
running = True


def receive_messages(sock):

    global show_timestamp, running

    while running:

        try:

            message = sock.recv(1024).decode()

            if not message:
                break

            msg = message

            if not show_timestamp and "[" in msg and "]" in msg:
                msg = msg.rsplit("[", 1)[0].strip() + "\n"

            sys.stdout.write("\r" + " " * 120 + "\r")

            print(msg, end="")

            sys.stdout.write("> ")
            sys.stdout.flush()

        except Exception:
            break

    running = False


def show_help():

    print("""

Commands:

/help
show help

/users
list online users

/msg USER MESSAGE
private message

/time on
show timestamps

/time off
hide timestamps

/quit
exit chat

""")


def send_messages(sock):

    global show_timestamp, running

    while running:

        try:

            msg = input("> ")

            if msg == "/help":
                show_help()
                continue

            if msg == "/time off":
                show_timestamp = False
                print("[Client] timestamps hidden")
                continue

            if msg == "/time on":
                show_timestamp = True
                print("[Client] timestamps enabled")
                continue

            if msg == "/quit":
                running = False
                sock.send(msg.encode())
                break

            sock.send(msg.encode())

        except Exception:
            break

    running = False


def start_client():

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.connect((SERVER_HOST, SERVER_PORT))
    except Exception as e:
        print("Connection failed:", e)
        return

    print(sock.recv(1024).decode(), end="")

    username = input()

    sock.send(username.encode())

    recv_thread = threading.Thread(
        target=receive_messages,
        args=(sock,),
        daemon=True
    )

    recv_thread.start()

    send_thread = threading.Thread(
        target=send_messages,
        args=(sock,),
        daemon=True
    )

    send_thread.start()

    send_thread.join()

    try:
        sock.shutdown(socket.SHUT_RDWR)
    except:
        pass

    sock.close()


if __name__ == "__main__":
    start_client()
