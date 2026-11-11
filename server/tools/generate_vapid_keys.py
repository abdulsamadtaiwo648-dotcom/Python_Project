"""Print a new VAPID key pair for SoloBiz push notifications.

Run once:  python -m server.tools.generate_vapid_keys
Then set VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY (and VAPID_SUBJECT) on the
host. Keep the private key secret, and keep the pair stable: changing it
invalidates every device that already turned notifications on.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate():
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64url(public_raw), _b64url(private_raw)


if __name__ == "__main__":
    public_key, private_key = generate()
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print("VAPID_SUBJECT=mailto:you@example.com  # replace with your support email or site URL")
