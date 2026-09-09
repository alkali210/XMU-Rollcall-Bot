"""Network failure classification shared by monitoring and API calls."""
import ssl
import requests

REQUEST_TIMEOUT = (10, 30)
RETRY_INITIAL_DELAY = 5
RETRY_MAX_DELAY = 60
MAX_RETRIES = 10


def _is_ssl_eof(exc):
    """Inspect nested Requests/urllib3 errors without retrying certificate failures."""
    pending = [exc]
    seen = set()
    eof = False
    while pending:
        error = pending.pop()
        if id(error) in seen:
            continue
        seen.add(id(error))
        if isinstance(error, ssl.SSLCertVerificationError):
            return False
        message = str(error)
        if "CERTIFICATE_VERIFY_FAILED" in message:
            return False
        if isinstance(error, ssl.SSLEOFError) or "UNEXPECTED_EOF_WHILE_READING" in message:
            eof = True
        pending.extend(value for value in (
            error.__cause__, error.__context__, getattr(error, "reason", None),
            *error.args,
        ) if isinstance(value, BaseException))
    return eof


def is_retryable(exc):
    # Certificate/configuration errors need operator attention.
    if isinstance(exc, requests.exceptions.SSLError):
        return _is_ssl_eof(exc)
    if isinstance(exc, (requests.ConnectionError, requests.Timeout,
                        requests.exceptions.ChunkedEncodingError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in (408, 429, 500, 502, 503, 504)
    return False
