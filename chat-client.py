import asyncio
import sys

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 12345


class ClientState:
    def __init__(self):
        self.show_timestamp = True
        self.connected = True


def clear_last_line():
    # move cursor up and clear line
    sys.stdout.write("\033[F")
    sys.stdout.write("\033[K")
    sys.stdout.flush()


async def receive_messages(reader: asyncio.StreamReader, state: ClientState):
    while state.connected:
        try:
            data = await reader.readline()

            if not data:
                print("\n[Client] Disconnected from server")
                state.connected = False
                break

            msg = data.decode(errors="replace")

            if not state.show_timestamp:
                if msg.rstrip().endswith("]") and "[" in msg:
                    head, sep, tail = msg.rpartition("[")
                    if ":" in tail and tail.strip("]\r\n").replace(":", "").isdigit():
                        msg = head.rstrip() + "\n"


            print(msg, end="")
            print("> ", end="", flush=True)

        except Exception as e:
            print(f"\n[Client] Error receiving data: {e}")
            state.connected = False
            break


async def send_messages(writer: asyncio.StreamWriter, state: ClientState):
    loop = asyncio.get_event_loop()

    while state.connected:
        try:
            msg = await loop.run_in_executor(None, input, "> ")
        except (EOFError, KeyboardInterrupt):
            msg = "/quit"

        if not msg.strip():
            continue

        # پاک کردن خطی که کاربر تایپ کرده
        clear_last_line()

        if msg == "/time off":
            state.show_timestamp = False
            print("[Client] Timestamps hidden")
            continue

        if msg == "/time on":
            state.show_timestamp = True
            print("[Client] Timestamps enabled")
            continue

        if msg == "/quit":
            writer.write(b"/quit\n")
            await writer.drain()
            state.connected = False
            break

        try:
            writer.write((msg + "\n").encode())
            await writer.drain()
        except Exception as e:
            print(f"\n[Client] Error sending message: {e}")
            state.connected = False
            break


async def main():
    try:
        reader, writer = await asyncio.open_connection(
            SERVER_HOST,
            SERVER_PORT
        )
    except Exception as e:
        print(f"[Client] Could not connect to server: {e}")
        return

    try:
        print((await reader.readline()).decode(), end="")
        print((await reader.readline()).decode(), end="")
    except:
        print("[Client] Server closed connection")
        return

    password = input()
    writer.write((password + "\n").encode())
    await writer.drain()

    line = await reader.readline()

    if not line:
        print("[Client] Connection closed")
        return

    text = line.decode()
    print(text, end="")

    if "Invalid password" in text:
        writer.close()
        await writer.wait_closed()
        return

    username = input().strip()
    writer.write((username + "\n").encode())
    await writer.drain()

    state = ClientState()

    recv_task = asyncio.create_task(receive_messages(reader, state))
    send_task = asyncio.create_task(send_messages(writer, state))

    await send_task

    state.connected = False
    recv_task.cancel()

    writer.close()
    await writer.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
