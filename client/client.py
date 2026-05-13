"""Terminal client for Secure Messenger.

Run:
    python -m client.client
"""

from __future__ import annotations

import json
import os
import threading
import time
from getpass import getpass
from typing import Any

import httpx

BASE_URL = os.getenv("SECURE_MESSENGER_BASE_URL", "http://127.0.0.1:8000")


class ApiError(Exception):
    """Raised for API-level failures (non-2xx responses)."""


def request_json(
    client: httpx.Client,
    method: str,
    path: str,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = client.request(method, f"{BASE_URL}{path}", headers=headers, json=payload)
    except httpx.RequestError as exc:
        raise ApiError(f"Cannot reach server: {exc}") from exc

    data: dict[str, Any] | list[Any]
    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code >= 400:
        if isinstance(data, dict):
            detail = data.get("detail")
            if isinstance(detail, str) and detail:
                raise ApiError(detail)
        raise ApiError(f"HTTP {response.status_code}")

    return data


def prompt_auth(client: httpx.Client) -> tuple[str, str]:
    """Interactive auth flow: register or login until successful login."""
    print("=== Secure Messenger ===")

    while True:
        print("1) Register")
        print("2) Login")
        choice = input("Choose (1/2): ").strip()

        if choice not in {"1", "2"}:
            print("Please choose 1 or 2.\n")
            continue

        username = input("Username: ").strip()
        password = getpass("Password: ")

        if not username or not password:
            print("Username and password are required.\n")
            continue

        if choice == "1":
            try:
                request_json(
                    client,
                    "POST",
                    "/register",
                    payload={"username": username, "password": password},
                )
                print("Account created. Please login.\n")
            except ApiError as exc:
                print(f"Register failed: {exc}\n")
            continue

        try:
            data = request_json(
                client,
                "POST",
                "/login",
                payload={"username": username, "password": password},
            )
        except ApiError as exc:
            print(f"Login failed: {exc}\n")
            continue

        if not isinstance(data, dict) or "access_token" not in data:
            print("Login failed: access token missing in response.\n")
            continue

        token = str(data["access_token"])
        return username, token


def print_history(client: httpx.Client, token: str, username: str) -> None:
    """Fetch and print current message history for this user."""
    try:
        data = request_json(client, "GET", "/messages", token=token)
    except ApiError as exc:
        print(f"Could not load history: {exc}")
        return

    if not isinstance(data, list) or not data:
        print("\nNo message history yet.")
        return

    print("\nRecent messages:")
    for message in data:
        if not isinstance(message, dict):
            continue

        sender = str(message.get("sender", "?"))
        recipient = str(message.get("recipient", "?"))
        content = str(message.get("content", ""))

        if sender == username:
            print(f"  [you -> {recipient}]: {content}")
        else:
            print(f"  [{sender} -> you]: {content}")


def listen_for_messages(base_url: str, token: str, username: str, stop_event: threading.Event) -> None:
    """Background SSE consumer that prints incoming messages in real time."""
    headers = {"Authorization": f"Bearer {token}"}
    timeout = httpx.Timeout(10.0, connect=5.0, read=5.0)

    while not stop_event.is_set():
        try:
            with httpx.stream("GET", f"{base_url}/stream", headers=headers, timeout=timeout) as response:
                if response.status_code == 401:
                    print("\nSession expired (401). Please login again.")
                    return

                if response.status_code != 200:
                    print(f"\nSSE stream error: HTTP {response.status_code}. Retrying...")
                    time.sleep(1.0)
                    continue

                for line in response.iter_lines():
                    if stop_event.is_set():
                        return

                    if not line or not line.startswith("data:"):
                        continue

                    payload = line[len("data:") :].strip()
                    if not payload:
                        continue

                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    if not isinstance(event, dict):
                        continue

                    sender = str(event.get("sender", "?"))
                    recipient = str(event.get("recipient", "?"))
                    content = str(event.get("content", ""))

                    # Only print incoming messages for this user.
                    if recipient != username or sender == username:
                        continue

                    print(f"\n  [{sender} -> {username}]: {content}")
                    print("  > ", end="", flush=True)

        except httpx.ReadTimeout:
            # Expected for long-lived streams with quiet periods.
            continue
        except httpx.RequestError as exc:
            if stop_event.is_set():
                return
            print(f"\nSSE connection issue: {exc}. Retrying...")
            time.sleep(1.0)


def main() -> None:
    with httpx.Client(timeout=10.0) as client:
        username, token = prompt_auth(client)

        print(f"\nWelcome, {username}! (type your message and press Enter, or 'quit' to exit)")
        print("Use '/to <username>' to switch recipient.")

        print_history(client, token, username)

        stop_event = threading.Event()
        listener_thread = threading.Thread(
            target=listen_for_messages,
            args=(BASE_URL, token, username, stop_event),
            daemon=True,
        )
        listener_thread.start()

        recipient = input("\nSend to username: ").strip()

        try:
            while True:
                text = input("  > ").strip()
                if not text:
                    continue

                if text.lower() in {"quit", "exit"}:
                    break

                if text.startswith("/to "):
                    next_recipient = text[4:].strip()
                    if not next_recipient:
                        print("Usage: /to <username>")
                        continue
                    recipient = next_recipient
                    print(f"Now sending to: {recipient}")
                    continue

                if not recipient:
                    print("No recipient set. Use '/to <username>'.")
                    continue

                try:
                    request_json(
                        client,
                        "POST",
                        "/messages",
                        token=token,
                        payload={"recipient": recipient, "content": text},
                    )
                except ApiError as exc:
                    print(f"Send failed: {exc}")

        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            stop_event.set()
            print("\nGoodbye.")


if __name__ == "__main__":
    main()
