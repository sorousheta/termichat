import socket
import threading
import sys

SERVER_HOST = ""
SERVER_PORT = 8080

show_timestamp = True

def receive_messages(sock):

    global show_timestamp

    while True:

        try:

            message = sock.recv(1024).decode()

            if not message:
                break

            msg = message

            if not show_timestamp and "[" in msg and "]" in msg:
                msg = msg.rsplit("[",1)[0].strip() + "\n"

            sys.stdout.write("\r" + " "*80 + "\r")

            print(msg,end="")

            sys.stdout.write("> ")
            sys.stdout.flush()

        except:
            break

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

    global show_timestamp

    while True:

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

                sock.send(msg.encode())
                break

            sock.send(msg.encode())

        except:
            break

def start_client():

    sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)

    sock.connect((SERVER_HOST,SERVER_PORT))

    print(sock.recv(1024).decode(),end="")

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
        args=(sock,)
    )

    send_thread.start()

    send_thread.join()

    sock.close()

if __name__ == "__main__":
    start_client()
