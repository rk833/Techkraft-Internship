"""Unit tests for the hashing and token primitives.

No HTTP here. These functions are the foundation everything else stands on, and
testing them directly means a failure names the actual cause rather than
surfacing as a confusing 401 three layers up.
"""

import time
from datetime import timedelta

import bcrypt
import jwt
import pytest

from app.config import Settings
from app.security import (
    MAX_PASSWORD_BYTES,
    UNUSABLE_PASSWORD,
    TokenError,
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)

SETTINGS = Settings(bcrypt_rounds=4, jwt_secret_key="x" * 48)


class TestHashing:
    def test_the_hash_is_not_the_password(self):
        hashed = hash_password("correct-horse", SETTINGS)
        assert "correct-horse" not in hashed

    def test_it_is_a_bcrypt_hash(self):
        assert hash_password("correct-horse", SETTINGS).startswith("$2b$")

    def test_the_same_password_hashes_differently_every_time(self):
        """bcrypt embeds a fresh random salt, which is what defeats rainbow tables.

        It is also why there is no separate salt column - the salt travels
        inside the hash string.
        """
        a = hash_password("same-password", SETTINGS)
        b = hash_password("same-password", SETTINGS)
        assert a != b

    def test_both_hashes_still_verify(self):
        for _ in range(3):
            assert verify_password("same-password", hash_password("same-password", SETTINGS), SETTINGS)

    def test_a_wrong_password_fails(self):
        assert not verify_password("wrong", hash_password("right-password", SETTINGS), SETTINGS)

    def test_verification_is_case_sensitive(self):
        assert not verify_password("PASSWORD1", hash_password("password1", SETTINGS), SETTINGS)

    def test_the_cost_factor_is_recorded_in_the_hash(self):
        assert hash_password("x", Settings(bcrypt_rounds=4)).split("$")[2] == "04"
        assert hash_password("x", Settings(bcrypt_rounds=5)).split("$")[2] == "05"

    def test_a_password_over_72_bytes_is_rejected(self):
        """bcrypt raises rather than truncating, so this must not reach it.

        The schema caps the field at 72, and this is the second line of
        defence. Silent truncation would be worse than an error: two different
        passwords sharing a 72-byte prefix would become the same password.
        """
        with pytest.raises(ValueError):
            hash_password("x" * (MAX_PASSWORD_BYTES + 1), SETTINGS)


class TestUnusablePassword:
    def test_nothing_verifies_against_it(self):
        """The value the migration backfills for legacy accounts."""
        for attempt in ("", "!", "password", UNUSABLE_PASSWORD):
            assert not verify_password(attempt, UNUSABLE_PASSWORD, SETTINGS)

    def test_a_missing_hash_never_verifies(self):
        assert not verify_password("anything", None, SETTINGS)

    def test_a_malformed_hash_fails_rather_than_raising(self):
        """A corrupt row is a failed login, not a 500."""
        assert not verify_password("anything", "not-a-bcrypt-hash", SETTINGS)


class TestTimingDefence:
    def test_a_missing_user_costs_about_the_same_as_a_wrong_password(self):
        """Guards against username enumeration by timing.

        verify_password runs a dummy bcrypt check when there is no hash, so an
        unknown username is not measurably faster than a known one. Without it
        the two differ by the entire cost of a bcrypt verification.
        """
        real = hash_password("real-password", SETTINGS)
        # Warm both paths so the dummy hash is already computed.
        verify_password("guess", real, SETTINGS)
        verify_password("guess", None, SETTINGS)

        def timed(hashed, rounds=15):
            start = time.perf_counter()
            for _ in range(rounds):
                verify_password("guess", hashed, SETTINGS)
            return (time.perf_counter() - start) / rounds

        with_user = timed(real)
        without_user = timed(None)
        ratio = max(with_user, without_user) / min(with_user, without_user)
        assert ratio < 3, f"with_user={with_user*1000:.2f}ms without_user={without_user*1000:.2f}ms"


class TestRehash:
    def test_an_old_hash_is_flagged(self):
        old = hash_password("password1", Settings(bcrypt_rounds=4))
        assert needs_rehash(old, Settings(bcrypt_rounds=6))

    def test_a_current_hash_is_not(self):
        current = hash_password("password1", Settings(bcrypt_rounds=5))
        assert not needs_rehash(current, Settings(bcrypt_rounds=5))

    def test_an_unparseable_hash_is_flagged(self):
        assert needs_rehash("garbage", SETTINGS)


class TestTokens:
    def test_a_token_round_trips(self):
        token = create_token(42, "access", "user", SETTINGS)
        claims = decode_token(token, "access", SETTINGS)
        assert claims["sub"] == "42"
        assert claims["role"] == "user"

    def test_sub_is_a_string_not_an_int(self):
        """The JWT spec says sub is a string, and some libraries enforce it."""
        assert isinstance(decode_token(create_token(42, "access", "user", SETTINGS), "access", SETTINGS)["sub"], str)

    def test_the_payload_is_readable_without_the_key(self):
        """A JWT is signed, not encrypted.

        Anyone holding the token can read every claim. That is why a token may
        carry an id and a role and must never carry anything secret.
        """
        token = create_token(42, "access", "admin", SETTINGS)
        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["role"] == "admin"

    def test_but_it_cannot_be_altered(self):
        """Readable is not the same as forgeable."""
        token = create_token(42, "access", "user", SETTINGS)
        claims = jwt.decode(token, options={"verify_signature": False})
        claims["role"] = "admin"
        forged = jwt.encode(claims, "the-wrong-key-" + "z" * 40, algorithm="HS256")
        with pytest.raises(TokenError):
            decode_token(forged, "access", SETTINGS)

    def test_a_token_signed_with_another_key_is_rejected(self):
        other = Settings(bcrypt_rounds=4, jwt_secret_key="y" * 48)
        token = create_token(42, "access", "admin", other)
        with pytest.raises(TokenError):
            decode_token(token, "access", SETTINGS)

    def test_an_expired_token_is_rejected(self):
        token = create_token(42, "access", "user", SETTINGS, expires_delta=timedelta(seconds=-1))
        with pytest.raises(TokenError, match="expired"):
            decode_token(token, "access", SETTINGS)

    def test_a_tampered_token_is_rejected(self):
        token = create_token(42, "access", "user", SETTINGS)
        header, payload, signature = token.split(".")
        with pytest.raises(TokenError):
            decode_token(f"{header}.{payload}.{signature[:-4]}abcd", "access", SETTINGS)

    @pytest.mark.parametrize("garbage", ["", "not-a-token", "a.b", "a.b.c.d"])
    def test_malformed_tokens_are_rejected(self, garbage):
        with pytest.raises(TokenError):
            decode_token(garbage, "access", SETTINGS)

    def test_a_refresh_token_is_not_an_access_token(self):
        """The check that stops a 7-day token acting as a 30-minute one."""
        refresh = create_token(42, "refresh", "user", SETTINGS)
        with pytest.raises(TokenError, match="access"):
            decode_token(refresh, "access", SETTINGS)

    def test_an_access_token_is_not_a_refresh_token(self):
        access = create_token(42, "access", "user", SETTINGS)
        with pytest.raises(TokenError, match="refresh"):
            decode_token(access, "refresh", SETTINGS)

    def test_the_alg_none_attack_is_rejected(self):
        """The classic JWT vulnerability.

        An unsigned token declaring alg=none is accepted by any decoder that
        trusts the token's own header. Passing algorithms= explicitly is what
        prevents it, and this test is why that argument is not optional.
        """
        claims = {"sub": "42", "type": "access", "role": "admin", "exp": 9999999999, "iat": 1}
        unsigned = jwt.encode(claims, key="", algorithm="none")
        with pytest.raises(TokenError):
            decode_token(unsigned, "access", SETTINGS)

    def test_each_token_has_a_unique_id(self):
        ids = {decode_token(create_token(1, "access", "user", SETTINGS), "access", SETTINGS)["jti"] for _ in range(5)}
        assert len(ids) == 5

    def test_a_refresh_token_lives_longer_than_an_access_token(self):
        access = decode_token(create_token(1, "access", "user", SETTINGS), "access", SETTINGS)
        refresh = decode_token(create_token(1, "refresh", "user", SETTINGS), "refresh", SETTINGS)
        assert refresh["exp"] > access["exp"]


class TestSecretValidation:
    def test_a_missing_secret_is_refused(self):
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is not set"):
            Settings(jwt_secret_key="").validate_secret()

    def test_a_short_secret_is_refused(self):
        with pytest.raises(RuntimeError, match="too short"):
            Settings(jwt_secret_key="short").validate_secret()

    def test_a_dev_secret_is_refused_in_production(self):
        with pytest.raises(RuntimeError, match="production"):
            Settings(jwt_secret_key="dev-" + "x" * 40, environment="production").validate_secret()

    def test_a_real_secret_is_accepted(self):
        Settings(jwt_secret_key="x" * 48).validate_secret()
