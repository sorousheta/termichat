import asyncio
import logging
from datetime import datetime
from collections import deque
import time
from typing import Dict, Optional

# =========================
# تنظیمات پایه سرور
# =========================
HOST = "0.0.0.0"
PORT = 12345

MAX_HISTORY = 50
SPAM_LIMIT = 5
SPAM_WINDOW = 1

# --- پسورد سرور (اینجا می‌تونی عوضش کنی) ---
SERVER_PASSWORD = "mysecretpassword"
# --------------------------------------------

# =========================
# تنظیمات لاگ حرفه‌ای
# =========================
# این فلگ‌ها را قبل از اجرای سرور می‌توانی تغییر بدهی
LOG_CHAT = True      # پیام‌های چت (عمومی و خصوصی)
LOG_SERVER = True    # رویدادهای سرور و خطاهای کلی
LOG_AUTH = True      # احراز هویت (ورود، تلاش پسورد اشتباه، ...)

CHAT_LOG_FILE = "chat.log"
SERVER_LOG_FILE = "server.log"
AUTH_LOG_FILE = "auth.log"


def create_logger(name: str, filename: str, enabled: bool) -> logging.Logger:
    """
    ساخت یک logger که همزمان:
      - در صورت enabled بودن در فایل بنویسد
      - همیشه روی stdout هم خروجی بدهد (برای journalctl)
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # جلوگیری از اضافه شدن چندباره هندلر در صورت ایمپورت مجدد
    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s %(message)s")

    # هندلر خروجی استاندارد (برای journalctl)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # هندلر فایل در صورت فعال بودن
    if enabled:
        file_handler = logging.FileHandler(filename, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# سه لاگر تخصصی
chat_logger = create_logger("chat", CHAT_LOG_FILE, LOG_CHAT)
server_logger = create_logger("server", SERVER_LOG_FILE, LOG_SERVER)
auth_logger = create_logger("auth", AUTH_LOG_FILE, LOG_AUTH)


# توابع کمکی برای لاگ‌کردن
def log_chat(message: str) -> None:
    """لاگ پیام‌های چت (عمومی و خصوصی)."""
    if LOG_CHAT:
        chat_logger.info(message)


def log_server(message: str) -> None:
    """لاگ رویدادهای سرور (start/stop، خطاها، اتصال/قطع اتصال و ...)."""
    if LOG_SERVER:
        server_logger.info(message)


def log_auth(message: str) -> None:
    """لاگ رویدادهای احراز هویت (پسورد درست/غلط، ورود، رد یوزرنیم و ...)."""
    if LOG_AUTH:
        auth_logger.info(message)


def log_server_exception(message: str) -> None:
    """لاگ استثناهای مربوط به سرور با traceback."""
    if LOG_SERVER:
        server_logger.exception(message)


def log_auth_exception(message: str) -> None:
    """لاگ استثناهای مربوط به احراز هویت با traceback."""
    if LOG_AUTH:
        auth_logger.exception(message)


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


HELP_TEXT = """
Commands:

/help
show help

/users
show online users

/msg USER MESSAGE
send private message

/quit
exit chat
"""


class ChatServer:
    def __init__(self):
        # writer -> username
        self.clients: Dict[asyncio.StreamWriter, str] = {}
        # username -> writer (برای lookup سریع‌تر)
        self.user_writers: Dict[str, asyncio.StreamWriter] = {}
        self.history = deque(maxlen=MAX_HISTORY)
        self.last_messages = {}  # writer -> [timestamps]

    async def send(self, writer: asyncio.StreamWriter, message: str) -> None:
        """ارسال یک پیام (یک خط) به یک کلاینت."""
        if not message:
            return

        try:
            writer.write((message + "\n").encode())
            await writer.drain()
        except ConnectionResetError:
            # کلاینت اتصال را بسته است؛ اجازه بده بالاتر هندل شود
            raise
        except Exception as e:
            # خطای زیرساختی ارسال پیام → لاگ در لاگر سرور
            log_server_exception(f"Error sending to client: {e}")
            raise

    async def broadcast(
        self,
        message: str,
        exclude: Optional[asyncio.StreamWriter] = None
    ) -> None:
        """ارسال پیام به همه کاربران آنلاین به جز 'exclude'."""
        dead = []

        for writer in list(self.clients.keys()):
            if writer is exclude:
                continue

            try:
                await self.send(writer, message)
            except Exception:
                dead.append(writer)

        # پاکسازی کلاینت‌هایی که مرده‌اند
        for d in dead:
            await self.disconnect(d)

    async def send_history(self, writer: asyncio.StreamWriter) -> None:
        """ارسال آخرین پیام‌های history برای کاربر تازه وارد."""
        if not self.history:
            return

        await self.send(writer, "[Server] Last messages:")

        for msg in self.history:
            await self.send(writer, msg)

    async def send_help(self, writer: asyncio.StreamWriter) -> None:
        """ارسال متن راهنما به یک کاربر."""
        for line in HELP_TEXT.strip().split("\n"):
            await self.send(writer, line)

    async def send_user_list(self, writer: asyncio.StreamWriter) -> None:
        """ارسال لیست کاربران آنلاین به صورت یک خط."""
        if not self.clients:
            await self.send(writer, "[Server] No users online")
            return

        users = ", ".join(sorted(self.clients.values()))
        await self.send(writer, f"[Server] Online users ({len(self.clients)}): {users}")

    def check_spam(self, writer: asyncio.StreamWriter) -> bool:
        """
        بررسی اسپم. اگر کاربر در یک پنجره زمانی مشخص بیشتر از
        SPAM_LIMIT پیام داده باشد، True برمی‌گرداند.
        """
        now = time.time()

        if writer not in self.last_messages:
            self.last_messages[writer] = []

        self.last_messages[writer].append(now)

        self.last_messages[writer] = [
            t for t in self.last_messages[writer]
            if now - t < SPAM_WINDOW
        ]

        return len(self.last_messages[writer]) > SPAM_LIMIT

    async def private_message(
        self,
        sender_writer: asyncio.StreamWriter,
        target: str,
        message: str
    ) -> None:
        """ارسال پیام خصوصی از sender به target."""
        sender = self.clients.get(sender_writer)

        # سعی می‌کنیم از map سریع‌تر استفاده کنیم
        target_writer = self.user_writers.get(target)

        if target_writer is None:
            await self.send(sender_writer, "[Server] User not found")
            return

        formatted = f"[PM] {sender} -> {target}: {message} [{timestamp()}]"

        # لاگ پیام خصوصی در لاگر چت
        log_chat(formatted)

        await self.send(target_writer, formatted)

        if target_writer is not sender_writer:
            await self.send(sender_writer, formatted)

    async def disconnect(self, writer: asyncio.StreamWriter) -> None:
        """قطع اتصال و پاکسازی منابع مربوط به یک کلاینت."""
        username = self.clients.pop(writer, None)

        if username:
            # پاک کردن از map معکوس
            self.user_writers.pop(username, None)

            log_server(f"[-] {username} disconnected")

            await self.broadcast(
                f"[Server] {username} left the chat",
                writer
            )

        self.last_messages.pop(writer, None)

        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

    async def handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        """هندل کردن یک کلاینت از لحظه اتصال تا قطع شدن."""
        addr = writer.get_extra_info("peername")

        # خوشامد اولیه و درخواست پسورد
        await self.send(writer, "Welcome to Async Chat Server")
        await self.send(writer, "Enter password:")

        # دریافت پسورد
        try:
            password_line = await reader.readline()
            if not password_line:
                # کلاینت قبل از ارسال پسورد قطع شد
                log_auth(f"[!] Client {addr} disconnected before sending password")
                return
            password = password_line.decode().strip()
        except Exception as e:
            log_auth_exception(f"Error reading password from {addr}: {e}")
            writer.close()
            return

        if password != SERVER_PASSWORD:
            await self.send(writer, "[Server] Invalid password")
            log_auth(f"[!] Invalid password attempt from {addr}")
            writer.close()
            return

        # درخواست یوزرنیم بعد از تأیید پسورد
        await self.send(writer, "Enter your username:")

        try:
            username_line = await reader.readline()
            if not username_line:
                log_auth(f"[!] Client {addr} disconnected before sending username")
                return
            username = username_line.decode().strip()
        except Exception as e:
            log_auth_exception(f"Error reading username from {addr}: {e}")
            writer.close()
            return

        if not username or len(username) > 20:
            await self.send(writer, "[Server] Invalid username")
            log_auth(f"[!] Rejected invalid username '{username}' from {addr}")
            writer.close()
            return

        if username in self.user_writers:
            await self.send(writer, "[Server] Username already taken")
            log_auth(f"[!] Rejected duplicate username '{username}' from {addr}")
            writer.close()
            return

        # ثبت کاربر در دو map
        self.clients[writer] = username
        self.user_writers[username] = writer

        # لاگ ورود موفق (هم در auth و هم در server)
        log_auth(f"[+] {username} authenticated successfully from {addr}")
        log_server(f"[+] {username} connected from {addr}")

        await self.send(writer, "[Server] Welcome!")
        await self.send_help(writer)

        await self.broadcast(
            f"[Server] {username} joined the chat",
            writer
        )

        await self.send_history(writer)

        try:
            while True:
                data = await reader.readline()

                if not data:
                    break

                message = data.decode().strip()

                # نادیده گرفتن پیام خالی (اگر به هر دلیل برسد)
                if not message:
                    continue

                if self.check_spam(writer):
                    await self.send(writer, "[Server] Slow down!")
                    continue

                if message.startswith("/"):
                    parts = message.split(" ", 2)
                    command = parts[0]

                    if command == "/help":
                        await self.send_help(writer)

                    elif command == "/users":
                        await self.send_user_list(writer)

                    elif command == "/msg":
                        if len(parts) < 3:
                            await self.send(
                                writer,
                                "[Server] Usage: /msg USER MESSAGE"
                            )
                            continue

                        # parts[1] = target username
                        target = parts[1]
                        pm_message = parts[2]

                        await self.private_message(
                            writer,
                            target,
                            pm_message
                        )

                    elif command == "/quit":
                        await self.send(writer, "[Server] Goodbye!")
                        break

                    else:
                        await self.send(
                            writer,
                            "[Server] Unknown command. Type /help"
                        )

                else:
                    # پیام عمومی
                    user = self.clients.get(writer, "Unknown")
                    formatted = f"[{timestamp()}] {user}: {message}"

                    # ذخیره در history
                    self.history.append(formatted)

                    # لاگ در فایل چت
                    log_chat(formatted)

                    # ارسال برای همه
                    await self.broadcast(formatted)
        except Exception as e:
            log_server_exception(f"Error with client {addr}: {e}")
        finally:
            await self.disconnect(writer)


async def main() -> None:
    server = ChatServer()

    server_coro = await asyncio.start_server(
        server.handle_client,
        HOST,
        PORT
    )

    addr = server_coro.sockets[0].getsockname()
    print(f"[Server] Serving on {addr}")
    log_server(f"[Server] Started on {addr}")

    async with server_coro:
        await server_coro.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Server] Shutting down...")
        log_server("[Server] Shutting down by KeyboardInterrupt")

# End of chat-server0.py (pro logging version)
