from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    hashed = hash_password("tractor-secret")
    assert hashed != "tractor-secret"
    assert verify_password("tractor-secret", hashed)
    assert not verify_password("wrong-password", hashed)


def test_token_round_trip():
    token = create_access_token("admin")
    assert decode_token(token) == "admin"


def test_decode_rejects_garbage():
    assert decode_token("not-a-jwt") is None
    assert decode_token("") is None
