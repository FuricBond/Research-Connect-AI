"""
A mail server for the isolated end-to-end stack: it accepts everything over SMTP, sends nothing on,
and shows what arrived over HTTP, so the suites read a confirmation link the way its recipient
would, and the backend runs with EMAIL_PROVIDER=smtp as in production. Standard library only; it
runs in the backend's :e2e image and is never part of the application's own Compose file.

    GET /messages?to=<address>    JSON list of {to, subject, text}, oldest first
"""
from __future__ import annotations

import asyncio
from email import message_from_bytes, policy
import json
from urllib.parse import parse_qs, urlsplit

MESSAGES: list[dict] = []


def _store(recipients: list[str], raw: bytes) -> None:
    message = message_from_bytes(raw, policy=policy.default)
    body = message.get_body(preferencelist=("plain",))
    text = body.get_content() if body else ""
    for recipient in recipients:
        MESSAGES.append({"to": recipient.lower(), "subject": str(message["Subject"]), "text": text})


async def smtp(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    async def say(line: str) -> None:
        writer.write(line.encode() + b"\r\n")
        await writer.drain()

    recipients: list[str] = []
    await say("220 mailsink")
    while line := await reader.readline():
        verb = line[:4].upper().strip()
        if verb in (b"EHLO", b"HELO"):
            await say("250 mailsink")
        elif verb == b"MAIL":
            recipients = []
            await say("250 ok")
        elif verb == b"RCPT":
            recipients.append(line.split(b"<", 1)[1].split(b">", 1)[0].decode())
            await say("250 ok")
        elif verb == b"DATA":
            await say("354 go on")
            lines: list[bytes] = []
            while (data := await reader.readline()) not in (b".\r\n", b""):
                lines.append(data[1:] if data.startswith(b"..") else data)
            _store(recipients, b"".join(lines))
            await say("250 ok")
        elif verb == b"QUIT":
            await say("221 bye")
            break
        else:
            await say("250 ok")
    writer.close()


async def http(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    request = await reader.readline()
    while (await reader.readline()) not in (b"\r\n", b""):
        pass
    wanted = parse_qs(urlsplit(request.split(b" ")[1].decode()).query).get("to", [None])[0]
    found = [m for m in MESSAGES if wanted is None or m["to"] == wanted.lower()]
    body = json.dumps(found).encode()
    writer.write(
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n".encode()
        + body
    )
    await writer.drain()
    writer.close()


async def main() -> None:
    await asyncio.start_server(smtp, "0.0.0.0", 1025)
    server = await asyncio.start_server(http, "0.0.0.0", 8025)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
