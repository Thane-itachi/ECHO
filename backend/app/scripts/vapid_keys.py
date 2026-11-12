"""Generate the VAPID keypair that signs this server's push notifications.

    python -m app.scripts.vapid_keys

Prints two lines to paste into backend/.env. Run it once per deployment and keep the
private key with the other secrets: rotating it invalidates every existing
subscription, so devices have to re-enable notifications.
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate() -> tuple[str, str]:
    """Return (public_key_b64url, private_key_der_b64).

    The private half is printed as base64 DER on a single line, because a PEM header
    contains spaces and an unquoted .env line would be truncated by the shell.
    `app.services.push.to_pem` rebuilds the PEM from it.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return _b64url(public_raw), _b64url(der)


if __name__ == "__main__":  # pragma: no cover
    public_key, private_key = generate()
    print("# Web Push: put both halves in backend/.env, then restart the API.")
    print("# The public key also reaches browsers, which is expected. The private one never does.")
    print(f"ECHO_VAPID_PUBLIC_KEY={public_key}")
    print(f"ECHO_VAPID_PRIVATE_KEY={private_key}")
    print("ECHO_VAPID_SUBJECT=mailto:you@yourdomain.com")
