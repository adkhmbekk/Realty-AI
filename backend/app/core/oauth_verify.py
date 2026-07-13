"""
Проверка подлинности ID-token'ов Google / Apple (вход из нативного приложения).

Токен — это подписанный провайдером JWT. Мы НЕ доверяем его содержимому, пока не
проверили подпись публичным ключом провайдера (JWKS) и не убедились, что токен
выписан ДЛЯ НАШЕГО приложения (aud) НАШИМ провайдером (iss) и не истёк (exp).

Ключи берём через pyjwt.PyJWKClient (сам кэширует их и обновляет по kid) — новых
зависимостей не добавляем. Сеть трогает только загрузка JWKS; чистая проверка
claims (`_verify_claims`) сетевого доступа не требует и покрыта юнит-тестами.
"""
from typing import Iterable, Optional

import jwt

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
APPLE_CERTS_URL = "https://appleid.apple.com/auth/keys"

# Google выписывает токены от двух вариантов issuer — принимаем оба.
GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
APPLE_ISSUERS = frozenset({"https://appleid.apple.com"})


class OAuthError(Exception):
    """Токен не прошёл проверку (подпись/aud/iss/exp/формат). Ключ — для перевода
    в понятную ошибку на роуте (обычно 401)."""

    def __init__(self, key: str = "auth_invalid_token"):
        self.key = key
        super().__init__(key)


def _verify_claims(
    token: str,
    key,
    algorithms: Iterable[str],
    audiences: Iterable[str],
    issuers: Iterable[str],
    leeway: int = 30,
) -> dict:
    """
    Проверить подпись и обязательные claims уже полученным ключом. Вынесено
    отдельно от загрузки JWKS, чтобы тестировать без сети (локально подписанным
    токеном). Любая ошибка → OAuthError (не даём наружу деталей крипто-ошибки).
    """
    auds = [a for a in audiences if a]
    if not auds:
        # Приложение не сконфигурировано (не заданы client_id) — принимать
        # токены нельзя, иначе aud не с чем сверять.
        raise OAuthError("oauth_not_configured")
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=list(algorithms),
            audience=auds,  # pyjwt примет токен, если его aud ∈ auds
            leeway=leeway,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise OAuthError() from exc
    # issuer сверяем вручную: у Google их два варианта (audience/exp pyjwt уже
    # проверил при decode).
    if claims.get("iss") not in set(issuers):
        raise OAuthError()
    return claims


# ── Ленивая инициализация JWKS-клиентов (кэшируют ключи между запросами) ──────
_google_jwks: Optional["jwt.PyJWKClient"] = None
_apple_jwks: Optional["jwt.PyJWKClient"] = None


def _google_client() -> "jwt.PyJWKClient":
    global _google_jwks
    if _google_jwks is None:
        _google_jwks = jwt.PyJWKClient(GOOGLE_CERTS_URL)
    return _google_jwks


def _apple_client() -> "jwt.PyJWKClient":
    global _apple_jwks
    if _apple_jwks is None:
        _apple_jwks = jwt.PyJWKClient(APPLE_CERTS_URL)
    return _apple_jwks


def verify_google_id_token(token: str, audiences: Iterable[str]) -> dict:
    """Проверить Google ID-token. Возвращает claims (sub, email, given_name,
    family_name, email_verified). При любой ошибке — OAuthError."""
    try:
        signing_key = _google_client().get_signing_key_from_jwt(token).key
    except jwt.PyJWTError as exc:
        raise OAuthError() from exc
    return _verify_claims(token, signing_key, ["RS256"], audiences, GOOGLE_ISSUERS)


def verify_apple_identity_token(token: str, audiences: Iterable[str]) -> dict:
    """Проверить Apple identity-token. Возвращает claims (sub, email). При любой
    ошибке — OAuthError."""
    try:
        signing_key = _apple_client().get_signing_key_from_jwt(token).key
    except jwt.PyJWTError as exc:
        raise OAuthError() from exc
    return _verify_claims(token, signing_key, ["RS256"], audiences, APPLE_ISSUERS)
