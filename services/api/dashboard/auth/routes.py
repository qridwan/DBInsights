"""HTTP surface of the account system: /v1/auth/*, plus the `current_user` dependency that guards
every other route."""

import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .service import AuthError, AuthService

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterBody(_Body):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    name: str = Field(default="", max_length=80)


class EmailBody(_Body):
    email: str = Field(max_length=254)


class ResendBody(EmailBody):
    purpose: str = Field(max_length=16)


class VerifyBody(EmailBody):
    code: str = Field(max_length=32)


class LoginBody(EmailBody):
    password: str = Field(max_length=256)


class ResetBody(VerifyBody):
    password: str = Field(max_length=256)


class ChangePasswordBody(_Body):
    current: str = Field(max_length=256)
    new: str = Field(max_length=256)


class ProfileBody(_Body):
    name: str = Field(max_length=80)


def get_auth(request: Request) -> AuthService:
    return request.app.state.auth


def bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else None


def client_ip(request: Request) -> str | None:
    # The dashboard's server forwards the visitor's address; without it we see only its own.
    return request.headers.get("x-client-ip") or (request.client.host if request.client else None)


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def current_user(
    request: Request, auth: Annotated[AuthService, Depends(get_auth)]
) -> dict[str, Any]:
    user = auth.authenticate(bearer(request))
    if user is None:
        raise AuthError("unauthenticated", "Sign in to continue.", 401)
    return user


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]
AuthDep = Annotated[AuthService, Depends(get_auth)]


def auth_error_response(_: Request, error: AuthError) -> JSONResponse:
    headers = (
        {"Retry-After": str(error.extra["retry_after"])} if "retry_after" in error.extra else None
    )
    return JSONResponse(
        status_code=error.status,
        content={"code": error.code, "message": error.message, **error.extra},
        headers=headers,
    )


def _signed_in(result: Any, claimed: int = 0) -> dict[str, Any]:
    return {
        "token": result.token,
        "expires_at": result.expires_at,
        "user": result.user,
        "claimed_projects": claimed,
    }


def _public(user: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in user.items() if k != "session"}


@router.post("/register", status_code=202)
def register(body: RegisterBody, auth: AuthDep) -> dict[str, Any]:
    return auth.register(body.email, body.password, body.name)


@router.post("/resend", status_code=202)
def resend(body: ResendBody, auth: AuthDep) -> dict[str, Any]:
    return auth.resend(body.email, body.purpose)


@router.post("/verify")
def verify(body: VerifyBody, request: Request, auth: AuthDep) -> dict[str, Any]:
    result = auth.verify_registration(
        body.email, body.code, client_ip(request), user_agent(request)
    )
    claimed = 0
    if result.became_admin:
        # The first account is the operator: it inherits what was scanned before accounts existed.
        claimed = request.app.state.store.claim_legacy_projects(result.user["id"])
    return _signed_in(result, claimed)


@router.post("/login")
def login(body: LoginBody, request: Request, auth: AuthDep) -> dict[str, Any]:
    return _signed_in(
        auth.login(body.email, body.password, client_ip(request), user_agent(request))
    )


@router.post("/logout", status_code=204)
def logout(request: Request, auth: AuthDep) -> Response:
    auth.logout(bearer(request))
    return Response(status_code=204)


@router.post("/forgot", status_code=202)
def forgot(body: EmailBody, auth: AuthDep) -> dict[str, Any]:
    return auth.forgot(body.email)


@router.post("/reset", status_code=204)
def reset(body: ResetBody, auth: AuthDep) -> Response:
    auth.reset(body.email, body.code, body.password)
    return Response(status_code=204)


@router.get("/me")
def me(user: CurrentUser) -> dict[str, Any]:
    return _public(user)


@router.patch("/me")
def update_me(body: ProfileBody, user: CurrentUser, auth: AuthDep) -> dict[str, Any]:
    auth.rename(user["id"], body.name)
    return {**_public(user), "name": body.name.strip()[:80]}


@router.post("/password", status_code=204)
def change_password(body: ChangePasswordBody, user: CurrentUser, auth: AuthDep) -> Response:
    auth.change_password(user["id"], body.current, body.new, keep_session=user["session"])
    return Response(status_code=204)


@router.get("/sessions")
def sessions(user: CurrentUser, auth: AuthDep) -> list[dict[str, Any]]:
    return auth.sessions(user["id"], user["session"])


@router.post("/sessions/revoke-others")
def revoke_others(user: CurrentUser, auth: AuthDep) -> dict[str, int]:
    return {"revoked": auth.sign_out_others(user["id"], user["session"])}


def admin_emails() -> tuple[str, ...]:
    return tuple(
        e.strip().lower()
        for e in os.environ.get("DBINSIGHT_ADMIN_EMAILS", "").split(",")
        if e.strip()
    )
