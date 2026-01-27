# -*- coding:utf-8 -*-
"""Auth controller with SIWE + UCAN support."""

from typing import Dict, Any
import os
import secrets
import time

from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_defunct
from flask import make_response, request
from jose import jwt, JWTError

from backend.common.middleware import handle_exceptions
from backend.common.response import ApiResponse
from backend.common.logger import get_logger
from backend.models.auth_challenge_response import AuthChallengeResponse
from backend.models.auth_challenge_response_body import AuthChallengeResponseBody
from backend.models.auth_verify_response import AuthVerifyResponse
from backend.models.auth_verify_response_body import AuthVerifyResponseBody
from backend.models.common_response_status import CommonResponseStatus, CommonResponseCodeEnum

# 加载环境变量
load_dotenv()

logger = get_logger(__name__)

# JWT 配置
JWT_SECRET = os.getenv(
    "JWT_SECRET",
    "e802e988a02546cc47415e4bc76346aae7ceece97a0f950319c861a5de38b20d",
)
JWT_ALGORITHM = "HS256"
ACCESS_TTL_MS = int(os.getenv("ACCESS_TTL_MS", str(15 * 60 * 1000)))
REFRESH_TTL_MS = int(os.getenv("REFRESH_TTL_MS", str(7 * 24 * 60 * 60 * 1000)))

COOKIE_SAMESITE_RAW = os.getenv("COOKIE_SAMESITE", "lax").lower()
COOKIE_SAMESITE = {
    "lax": "Lax",
    "strict": "Strict",
    "none": "None",
}.get(COOKIE_SAMESITE_RAW, "Lax")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "").lower() in ("1", "true", "yes")

# 内存存储（生产环境请替换为 Redis）
challenges: Dict[str, Dict[str, Any]] = {}
refresh_store: Dict[str, Dict[str, Any]] = {}


def now_ms() -> int:
    return int(time.time() * 1000)


def extract_request_value(payload: Any, key: str):
    if isinstance(payload, dict):
        if key in payload:
            return payload.get(key)
        body = payload.get("body")
        if isinstance(body, dict) and key in body:
            return body.get(key)
    return None


def issue_tokens(address: str):
    refresh_id = secrets.token_hex(16)
    refresh_expires_at = now_ms() + REFRESH_TTL_MS
    refresh_store[refresh_id] = {"address": address, "expiresAt": refresh_expires_at}

    refresh_token = jwt.encode(
        {
            "address": address,
            "typ": "refresh",
            "jti": refresh_id,
            "exp": int(time.time() + REFRESH_TTL_MS / 1000),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    access_token = jwt.encode(
        {
            "sub": address,
            "address": address,
            "typ": "access",
            "sid": refresh_id,
            "exp": int(time.time() + ACCESS_TTL_MS / 1000),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    return access_token, now_ms() + ACCESS_TTL_MS, refresh_expires_at, refresh_token


def set_refresh_cookie(response, token: str, max_age: int):
    response.set_cookie(
        "refresh_token",
        token,
        max_age=max_age,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/api/v1/auth",
    )


def clear_refresh_cookie(response):
    response.set_cookie(
        "refresh_token",
        "",
        max_age=0,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/api/v1/auth",
    )


@handle_exceptions
def auth_challenge(body):  # noqa: E501
    """获取挑战"""
    logger.info("authChallenge request.body=%s", body)
    address = extract_request_value(body, "address")
    if not address:
        return ApiResponse.bad_request("address 字段不能为空")

    nonce = secrets.token_hex(8)
    issued_at = now_ms()
    expires_at = issued_at + 5 * 60 * 1000
    challenge = f"Sign to login YeYing Interviewer\n\nnonce: {nonce}\nissuedAt: {issued_at}"

    addr_key = address.lower()
    challenges[addr_key] = {
        "challenge": challenge,
        "issuedAt": issued_at,
        "expiresAt": expires_at,
    }

    logger.info("Generated challenge for %s", addr_key)
    return AuthChallengeResponse(
        body=AuthChallengeResponseBody(
            status=CommonResponseStatus(CommonResponseCodeEnum.OK),
            result=challenge,
        )
    )


@handle_exceptions
def auth_verify(body):  # noqa: E501
    """验证签名"""
    logger.info("authVerify request.body=%s", body)
    address = extract_request_value(body, "address")
    signature = extract_request_value(body, "signature")
    if not address or not signature:
        return ApiResponse.bad_request("address 或 signature 不能为空")

    addr_key = address.lower()
    record = challenges.get(addr_key)

    if not record or now_ms() > record.get("expiresAt", 0):
        challenges.pop(addr_key, None)
        return ApiResponse.bad_request("Challenge 不存在或已过期")

    try:
        message = encode_defunct(text=record["challenge"])
        recovered_address = Account.recover_message(message, signature=signature)
        if recovered_address.lower() != addr_key:
            return ApiResponse.error("签名验证失败", code=401)
    except Exception as e:
        logger.warning("Signature verification failed: %s", e)
        return ApiResponse.error("签名验证失败", code=401)

    challenges.pop(addr_key, None)

    access_token, access_expires_at, refresh_expires_at, refresh_token = issue_tokens(addr_key)

    response_data = AuthVerifyResponse(
        body=AuthVerifyResponseBody(
            status=CommonResponseStatus(CommonResponseCodeEnum.OK),
            token=access_token,
        )
    )

    response = make_response(response_data.to_dict())

    # 设置 Cookie（页面访问鉴权）
    response.set_cookie(
        "auth_token",
        access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=int(ACCESS_TTL_MS / 1000),
    )

    # 设置 refresh cookie（API 刷新 token）
    set_refresh_cookie(response, refresh_token, int(REFRESH_TTL_MS / 1000))

    response.headers["Content-Type"] = "application/json"
    return response


@handle_exceptions
def auth_refresh():  # noqa: E501
    """刷新 access token"""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return ApiResponse.error("缺少刷新令牌", code=401)

    try:
        payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        response, status = ApiResponse.error("无效的刷新令牌", code=401)
        clear_refresh_cookie(response)
        return response, status

    if payload.get("typ") != "refresh" or not payload.get("jti"):
        response, status = ApiResponse.error("无效的刷新令牌", code=401)
        clear_refresh_cookie(response)
        return response, status

    record = refresh_store.get(payload["jti"])
    if not record or record.get("address") != payload.get("address") or now_ms() > record.get("expiresAt", 0):
        refresh_store.pop(payload["jti"], None)
        response, status = ApiResponse.error("刷新令牌已过期", code=401)
        clear_refresh_cookie(response)
        return response, status

    refresh_store.pop(payload["jti"], None)
    access_token, access_expires_at, refresh_expires_at, new_refresh_token = issue_tokens(payload["address"])

    response_data = AuthVerifyResponse(
        body=AuthVerifyResponseBody(
            status=CommonResponseStatus(CommonResponseCodeEnum.OK),
            token=access_token,
        )
    )

    response = make_response(response_data.to_dict())
    response.set_cookie(
        "auth_token",
        access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=int(ACCESS_TTL_MS / 1000),
    )
    set_refresh_cookie(response, new_refresh_token, int(REFRESH_TTL_MS / 1000))
    response.headers["Content-Type"] = "application/json"
    return response


@handle_exceptions
def auth_logout():
    """退出登录 - 清除 Cookie"""
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            jti = payload.get("jti")
            if jti:
                refresh_store.pop(jti, None)
        except Exception:
            pass

    response = make_response(
        {
            "status": {"code": "RESPONSE_CODE_OK", "message": "退出成功"}
        }
    )

    response.set_cookie("auth_token", "", expires=0)
    clear_refresh_cookie(response)
    response.headers["Content-Type"] = "application/json"
    return response
