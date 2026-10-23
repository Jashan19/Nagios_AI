import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from google import genai
from database import initialize_database
import hashlib
import hmac
import secrets
import time
import uuid
import sqlite3

from pathlib import Path
from fastapi import Cookie, Depends, Response
from fastapi.responses import FileResponse

from database import database_connection, initialize_database
load_dotenv()
SESSION_SECRET = os.getenv("SESSION_SECRET")

if not SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET is missing from .env")

SESSION_MAX_AGE = 7 * 24 * 60 * 60
BASE_DIR = Path(__file__).resolve().parent
api_key = os.getenv("GEMINI_API_KEY")
model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY is missing from .env")

client = genai.Client(api_key=api_key)
app = FastAPI()

initialize_database()

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)

    hashed = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
    )

    return f"{salt.hex()}${hashed.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, hash_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)

        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
        )

        return hmac.compare_digest(actual, expected)

    except (ValueError, TypeError):
        return False


def create_session(user_id: str) -> str:
    timestamp = str(int(time.time()))
    payload = f"{user_id}.{timestamp}"

    signature = hmac.new(
        SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    return f"{payload}.{signature}"


def session_user_id(session: str | None) -> str | None:
    if not session:
        return None

    try:
        user_id, timestamp, signature = session.split(".")

        payload = f"{user_id}.{timestamp}"

        expected = hmac.new(
            SESSION_SECRET.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            return None

        issued_at = int(timestamp)
        now = int(time.time())

        if issued_at > now or now - issued_at > SESSION_MAX_AGE:
            return None

        with database_connection() as db:
            user = db.execute(
                "SELECT id FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()

        return user_id if user else None

    except (ValueError, TypeError):
        return None


def get_current_user(
    session: str | None = Cookie(default=None),
) -> str:
    user_id = session_user_id(session)

    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=401,
            detail="Please log in first.",
        )

    return user_id


def set_session_cookie(response: Response, user_id: str):
    response.set_cookie(
        key="session",
        value=create_session(user_id),
        httponly=True,
        secure=False,  # Local HTTP development only.
        samesite="lax",
        max_age=SESSION_MAX_AGE,
        path="/",
    )
from pydantic import BaseModel


class AuthRequest(BaseModel):
    username: str
    password: str
class Message(BaseModel):
    role: str
    content: str
class PersistentChatRequest(BaseModel):
    conversation_id: str
    messages: list[Message]

@app.post("/api/signup")
def signup(data: AuthRequest, response: Response):
    username = data.username.strip()

    if not 3 <= len(username) <= 30:
        raise HTTPException(
            400, "Username must be 3–30 characters."
        )

    if not all(c.isalnum() or c in "_-" for c in username):
        raise HTTPException(
            400, "Use only letters, numbers, underscores, and hyphens."
        )

    if len(data.password) < 8:
        raise HTTPException(
            400, "Password must contain at least 8 characters."
        )

    user_id = str(uuid.uuid4())
    password_hash = hash_password(data.password)

    try:
        with database_connection() as db:
            db.execute(
                """
                INSERT INTO users
                    (id, username, display_name, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, username, username, password_hash),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(
            409, "That username is already taken."
        )

    set_session_cookie(response, user_id)

    return {"username": username}


@app.post("/api/login")
def login(data: AuthRequest, response: Response):
    username = data.username.strip()

    with database_connection() as db:
        user = db.execute(
            """
            SELECT id, username, password_hash
            FROM users
            WHERE username = ? COLLATE NOCASE
            """,
            (username,),
        ).fetchone()

    if not user or not user["password_hash"]:
        raise HTTPException(401, "Invalid username or password.")

    if not verify_password(data.password, user["password_hash"]):
        raise HTTPException(401, "Invalid username or password.")

    set_session_cookie(response, user["id"])

    return {"username": user["username"]}


@app.get("/api/me")
def me(user_id: str = Depends(get_current_user)):
    with database_connection() as db:
        user = db.execute(
            "SELECT username FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    return {"username": user["username"]}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(
        key="session",
        path="/",
        httponly=True,
        secure=False,
        samesite="lax",
    )

    return {"message": "Logged out"}
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


# @app.post("/api/chat")
# def chat(request: ChatRequest,  user_id: str = Depends(get_current_user),
# ):
#     if not request.messages:
#         raise HTTPException(400, "No messages provided")

#     contents = []

#     for message in request.messages[-20:]:
#         if message.role not in ("user", "assistant"):
#             continue

#         contents.append({
#             "role": "user" if message.role == "user" else "model",
#             "parts": [{"text": message.content}]
#         })

#     if not contents or contents[-1]["role"] != "user":
#         raise HTTPException(400, "Last message must be from the user")

#     try:
#         response = client.models.generate_content(
#             model=model_name,
#             contents=contents
#         )
#         return {
#             "reply": response.text or "I couldn't generate a response."
#         }

#     except Exception as e:
#         # Useful during local development
#         print("Gemini API error:", repr(e))
#         raise HTTPException(
#             status_code=502,
#             detail=f"Gemini API error: {type(e).__name__}: {e}"
#         )

@app.post("/api/chat")
def chat(
    request: PersistentChatRequest,
    user_id: str = Depends(get_current_user),
):
    if not request.messages:
        raise HTTPException(400, "No messages provided.")

    valid_messages = [
        message for message in request.messages[-20:]
        if message.role in ("user", "assistant")
    ]

    if not valid_messages or valid_messages[-1].role != "user":
        raise HTTPException(400, "Last message must be from the user.")

    with database_connection() as db:
        conversation = db.execute(
            """
            SELECT id FROM conversations
            WHERE id = ? AND user_id = ?
            """,
            (request.conversation_id, user_id),
        ).fetchone()

        if not conversation:
            raise HTTPException(404, "Conversation not found.")

        # Save the current conversation history.
        db.execute(
            "DELETE FROM messages WHERE conversation_id = ?",
            (request.conversation_id,),
        )

        for message in valid_messages:
            db.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (?, ?, ?)
                """,
                (request.conversation_id, message.role, message.content),
            )

        title = valid_messages[0].content[:32]
        if len(valid_messages[0].content) > 32:
            title += "..."

        db.execute(
            """
            UPDATE conversations
            SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (title, request.conversation_id, user_id),
        )

    contents = [
        {
            "role": "user" if message.role == "user" else "model",
            "parts": [{"text": message.content}],
        }
        for message in valid_messages
    ]

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
        )
        reply = response.text or "I couldn't generate a response."

    except Exception as e:
        print("Gemini API error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail=f"Gemini API error: {type(e).__name__}: {e}",
        )

    with database_connection() as db:
        db.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (?, 'assistant', ?)
            """,
            (request.conversation_id, reply),
        )

        db.execute(
            """
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (request.conversation_id,),
        )

    return {"reply": reply}

@app.get("/api/conversations")
def list_conversations(user_id: str = Depends(get_current_user)):
    with database_connection() as db:
        rows = db.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]


@app.post("/api/conversations")
def create_conversation(user_id: str = Depends(get_current_user)):
    conversation_id = str(uuid.uuid4())

    with database_connection() as db:
        db.execute(
            """
            INSERT INTO conversations (id, user_id, title)
            VALUES (?, ?, 'New chat')
            """,
            (conversation_id, user_id),
        )

    return {"id": conversation_id, "title": "New chat"}


@app.get("/api/conversations")
def get_conversations(user_id: str = Depends(get_current_user)):
    with database_connection() as db:
        rows = db.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at
            FROM conversations c
            WHERE c.user_id = ?
              AND EXISTS (
                  SELECT 1
                  FROM messages m
                  WHERE m.conversation_id = c.id
              )
            ORDER BY c.updated_at DESC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]


@app.get("/api/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: str,
    user_id: str = Depends(get_current_user),
):
    with database_connection() as db:
        conversation = db.execute(
            """
            SELECT id FROM conversations
            WHERE id = ? AND user_id = ?
            """,
            (conversation_id, user_id),
        ).fetchone()

        if not conversation:
            raise HTTPException(404, "Conversation not found.")

        rows = db.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id
            """,
            (conversation_id,),
        ).fetchall()

    return [dict(row) for row in rows]


@app.get("/", include_in_schema=False)
def home(session: str | None = Cookie(default=None)):
    if session_user_id(session):
        return FileResponse(BASE_DIR / "index.html")

    return FileResponse(BASE_DIR / "login.html")


# Keep this mount at the very bottom, after all routes.
app.mount(
    "/",
    StaticFiles(
        directory=os.path.dirname(os.path.abspath(__file__)),
        html=True,
    ),
    name="frontend",
)