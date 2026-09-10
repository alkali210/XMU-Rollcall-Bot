"""Network failure classification shared by monitoring and API calls."""
import ssl
import requests

REQUEST_TIMEOUT = (10, 30)
RETRY_INITIAL_DELAY = 5
RETRY_MAX_DELAY = 60
RETRY_MAX_ATTEMPTS = 10


def _is_ssl_eof(exc):
    # Requests/urllib3 wrap SSL errors in args and MaxRetryError.reason.
    pending = [exc]
    seen = set()
    while pending:
        error = pending.pop()
        if id(error) in seen:
            continue
        seen.add(id(error))
        if isinstance(error, ssl.SSLEOFError):
            return True
        if "UNEXPECTED_EOF_WHILE_READING" in str(error):
            return True
        pending.extend(arg for arg in error.args if isinstance(arg, BaseException))
        for nested in (getattr(error, "reason", None), error.__cause__, error.__context__):
            if isinstance(nested, BaseException):
                pending.append(nested)
    return False


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
