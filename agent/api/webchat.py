"""Public webchat API dùng widget token ký theo account và Origin."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent import db
from agent.channels.webchat import WebchatAdapter
from agent.config import settings
from agent.omnichannel.account_repository import PostgresAccountRepository
from agent.omnichannel.accounts import AccountStatus, Channel
from agent.omnichannel.credential_loader import VaultCredentialLoader
from agent.security.credential_vault import CredentialVault, parse_master_keys


router = APIRouter(prefix="/webchat", tags=["public-webchat"])


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_widget_token(
    *,
    secret: str,
    account_id: UUID,
    visitor_id: UUID,
    origin: str,
    now: int | None = None,
    ttl_seconds: int = 86400,
) -> str:
    issued = int(time.time()) if now is None else int(now)
    claims = {
        "account_id": str(account_id),
        "visitor_id": str(visitor_id),
        "origin": origin,
        "iat": issued,
        "exp": issued + max(60, min(ttl_seconds, 7 * 86400)),
    }
    payload = _b64(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    )
    signature = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def verify_widget_token(
    token: str,
    *,
    secret: str,
    account_id: UUID,
    origin: str,
    now: int | None = None,
) -> dict[str, Any]:
    try:
        payload, supplied = token.split(".", 1)
        expected = _b64(
            hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("widget token sai chữ ký")
        claims = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("widget token không hợp lệ") from exc
    current = int(time.time()) if now is None else int(now)
    if claims.get("account_id") != str(account_id):
        raise ValueError("widget token sai account")
    if claims.get("origin") != origin:
        raise ValueError("widget token sai origin")
    if int(claims.get("exp") or 0) < current:
        raise ValueError("widget token đã hết hạn")
    return claims


async def _account_credentials(account_id: UUID):
    repository = PostgresAccountRepository()
    account = await repository.get(account_id)
    if (
        account is None
        or account.channel != Channel.WEBCHAT
        or account.status not in {AccountStatus.ACTIVE, AccountStatus.DEGRADED}
    ):
        raise HTTPException(404, "Webchat account không hoạt động")
    try:
        vault = CredentialVault(
            parse_master_keys(settings.credential_master_keys),
            active_version=settings.credential_active_key_version,
        )
    except ValueError as exc:
        raise HTTPException(503, "Kho credential webchat chưa sẵn sàng") from exc
    credentials = await VaultCredentialLoader(repository, vault).load(account_id)
    if not credentials or not credentials.get("widget_secret"):
        raise HTTPException(409, "Webchat account thiếu widget secret")
    return account, credentials


def _origin_allowed(origin: str, credentials: dict[str, Any]) -> bool:
    allowed = credentials.get("allowed_origins") or []
    if isinstance(allowed, str):
        allowed = [allowed]
    return origin in {str(item).rstrip("/") for item in allowed}


def _cors(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Vary"] = "Origin"


class WebchatSessionIn(BaseModel):
    visitor_id: UUID | None = None


class WebchatMessageIn(BaseModel):
    client_message_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=4000)
    visitor_name: str = Field(default="Khách website", max_length=120)


@router.options("/{account_id}/{path:path}")
async def webchat_preflight(
    account_id: UUID,
    path: str,
    request: Request,
) -> Response:
    _account, credentials = await _account_credentials(account_id)
    origin = request.headers.get("origin", "").rstrip("/")
    if not origin or not _origin_allowed(origin, credentials):
        raise HTTPException(403, "Origin không được phép dùng webchat")
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Authorization,Content-Type",
            "Access-Control-Max-Age": "600",
            "Vary": "Origin",
        },
    )


async def _authorize(account_id: UUID, request: Request):
    _account, credentials = await _account_credentials(account_id)
    origin = request.headers.get("origin", "").rstrip("/")
    if not origin or not _origin_allowed(origin, credentials):
        raise HTTPException(403, "Origin không được phép dùng webchat")
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Thiếu widget token")
    try:
        claims = verify_widget_token(
            authorization[7:],
            secret=str(credentials["widget_secret"]),
            account_id=account_id,
            origin=origin,
        )
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc
    return credentials, origin, claims


@router.post("/{account_id}/session")
async def create_webchat_session(
    account_id: UUID,
    body: WebchatSessionIn,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _account, credentials = await _account_credentials(account_id)
    origin = request.headers.get("origin", "").rstrip("/")
    if not origin or not _origin_allowed(origin, credentials):
        raise HTTPException(403, "Origin không được phép dùng webchat")
    visitor_id = body.visitor_id or uuid4()
    token = issue_widget_token(
        secret=str(credentials["widget_secret"]),
        account_id=account_id,
        visitor_id=visitor_id,
        origin=origin,
    )
    _cors(response, origin)
    return {"visitor_id": str(visitor_id), "token": token, "expires_in": 86400}


@router.post("/{account_id}/messages", status_code=202)
async def send_webchat_message(
    account_id: UUID,
    body: WebchatMessageIn,
    request: Request,
    response: Response,
    tasks: BackgroundTasks,
) -> dict[str, Any]:
    credentials, origin, claims = await _authorize(account_id, request)
    adapter = WebchatAdapter(account_id=account_id, credentials=credentials)
    message = adapter.parse(
        {
            "visitor_id": claims["visitor_id"],
            "client_message_id": body.client_message_id,
            "visitor_name": body.visitor_name,
            "text": body.text,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    if message is None:
        raise HTTPException(422, "Tin webchat không hợp lệ")
    from agent.main import handle_inbound

    tasks.add_task(handle_inbound, message)
    _cors(response, origin)
    return {"ok": True, "queued": True, "client_message_id": body.client_message_id}


@router.get("/{account_id}/history")
async def webchat_history(
    account_id: UUID,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _credentials, origin, claims = await _authorize(account_id, request)
    rows = await db.fetch(
        """
        SELECT message.id, message.role, message.content, message.delivery_status,
               message.created_at
        FROM conversations conversation
        JOIN messages message ON message.conversation_id = conversation.id
        WHERE conversation.account_id = $1 AND conversation.external_id = $2
        ORDER BY message.created_at, message.id
        LIMIT 500
        """,
        account_id,
        claims["visitor_id"],
    )
    _cors(response, origin)
    return {"items": [dict(row) for row in rows]}


async def _webchat_events(account_id: UUID, visitor_id: str):
    last_seen = datetime.fromtimestamp(0, timezone.utc)
    while True:
        rows = await db.fetch(
            """
            SELECT message.id, message.role, message.content,
                   message.delivery_status, message.created_at
            FROM conversations conversation
            JOIN messages message ON message.conversation_id = conversation.id
            WHERE conversation.account_id = $1
              AND conversation.external_id = $2
              AND message.created_at > $3
            ORDER BY message.created_at, message.id
            LIMIT 100
            """,
            account_id,
            visitor_id,
            last_seen,
        )
        if rows:
            for row in rows:
                last_seen = max(last_seen, row["created_at"])
                data = json.dumps(dict(row), default=str, ensure_ascii=False)
                yield f"event: message\ndata: {data}\n\n"
        else:
            yield ": keep-alive\n\n"
        await asyncio.sleep(1)


@router.get("/{account_id}/events")
async def webchat_events(account_id: UUID, request: Request) -> StreamingResponse:
    _credentials, origin, claims = await _authorize(account_id, request)
    return StreamingResponse(
        _webchat_events(account_id, claims["visitor_id"]),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
        },
    )
