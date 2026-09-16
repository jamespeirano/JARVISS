"""HTTPS trust that travels with the app, including on a clean computer."""
import ssl
from functools import lru_cache

import certifi


@lru_cache(maxsize=1)
def tls_context():
    # Keep platform trust where available, then add our bundled Mozilla roots.
    # Frozen Python may otherwise look for the build machine's OpenSSL files.
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context
