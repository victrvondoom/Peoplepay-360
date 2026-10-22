"""Request-size limits, defined ONCE.

Three places used to disagree about the largest image a user could send: the browser accepted 4 MiB, the HTTP layer
refused any body over 1 MiB (so anything past ~750 KB of image failed with an opaque error), and the documentation
promised 32 MB. The HTTP layer and the service layer now both derive their limits from these constants, and the
browser's 4 MiB check is the same number as ``MAX_IMAGE_BYTES``.
"""
from __future__ import annotations

MAX_TEXT_CHARS = 100_000
MAX_IMAGE_BYTES = 4 * 1024 * 1024          # decoded bytes of one image
MAX_FILE_BYTES = 4 * 1024 * 1024           # decoded bytes of one file
MAX_ATTACHMENTS = 4
MAX_ATTACHMENT_BYTES_TOTAL = 8 * 1024 * 1024
IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")

#: Room in a JSON body for everything that is not an attachment: the text (up to 100k characters, which may be
#: multi-byte and JSON-escaped), selection, preferences.
_BODY_OVERHEAD_BYTES = 1024 * 1024


def base64_length(raw_bytes: int) -> int:
    """Length of the padded base64 text for ``raw_bytes`` of data."""
    return 4 * ((raw_bytes + 2) // 3)


#: Largest JSON body the model endpoints accept. Derived, so it cannot drift from what the service layer validates.
MAX_MODEL_BODY_BYTES = base64_length(MAX_ATTACHMENT_BYTES_TOTAL) + _BODY_OVERHEAD_BYTES
