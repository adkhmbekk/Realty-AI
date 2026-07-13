"""
Проверка подлинности OAuth ID-token (app/core/oauth_verify).

Критично для безопасности: убеждаемся, что _verify_claims РЕАЛЬНО отвергает
подделки — чужую подпись, чужой aud (токен, выписанный для другого приложения),
чужой iss, истёкший токен. Токены подписываем локально сгенерированным RSA-ключом
(без сети): валидные — своим ключом, «подделку подписи» — другим.
"""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core import oauth_verify
from app.core.oauth_verify import OAuthError

_AUD = "my-app.apps.googleusercontent.com"
_ISS = "https://accounts.google.com"


def _rsa():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(priv, *, aud=_AUD, iss=_ISS, sub="google-sub-1", exp_delta=3600, **extra):
    now = int(time.time())
    payload = {"sub": sub, "aud": aud, "iss": iss, "iat": now, "exp": now + exp_delta}
    payload.update(extra)
    return jwt.encode(payload, priv, algorithm="RS256")


def _verify(priv_for_verify, token):
    """Проверить token публичным ключом от priv_for_verify."""
    return oauth_verify._verify_claims(
        token, priv_for_verify.public_key(), ["RS256"], [_AUD], oauth_verify.GOOGLE_ISSUERS
    )


def test_accepts_valid_token():
    priv = _rsa()
    claims = _verify(priv, _token(priv, email="a@b.c"))
    assert claims["sub"] == "google-sub-1"
    assert claims["email"] == "a@b.c"


def test_rejects_forged_signature():
    """Токен подписан ЧУЖИМ ключом → подпись не сходится с нашим публичным."""
    signer, attacker = _rsa(), _rsa()
    token = _token(signer)  # подписан signer
    with pytest.raises(OAuthError):
        _verify(attacker, token)  # проверяем ключом attacker → не сойдётся


def test_rejects_wrong_audience():
    """Токен выписан для ДРУГОГО приложения (aud) → отвергаем."""
    priv = _rsa()
    token = _token(priv, aud="someone-elses-app")
    with pytest.raises(OAuthError):
        _verify(priv, token)


def test_rejects_wrong_issuer():
    priv = _rsa()
    token = _token(priv, iss="https://evil.example.com")
    with pytest.raises(OAuthError):
        _verify(priv, token)


def test_rejects_expired_token():
    priv = _rsa()
    token = _token(priv, exp_delta=-120)  # истёк 2 мин назад (за пределами leeway)
    with pytest.raises(OAuthError):
        _verify(priv, token)


def test_rejects_when_no_audiences_configured():
    """Не заданы client_id (aud не с чем сверять) → не принимаем токен."""
    priv = _rsa()
    token = _token(priv)
    with pytest.raises(OAuthError):
        oauth_verify._verify_claims(
            token, priv.public_key(), ["RS256"], [], oauth_verify.GOOGLE_ISSUERS
        )
