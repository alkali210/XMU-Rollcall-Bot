"""Shared LNT request settings and network failure classification."""
import ssl
import requests

REQUEST_TIMEOUT = (10, 30)
RETRY_INITIAL_DELAY = 5
RETRY_MAX_DELAY = 60
RETRY_MAX_ATTEMPTS = 10

BASE_URL = "https://lnt.xmu.edu.cn"
USER_AGENT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
}
BROWSER_HEADERS = {
    **USER_AGENT_HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://ids.xmu.edu.cn/authserver/login",
}


def api_headers(session):
    """Preserve session authentication headers while selecting JSON API headers."""
    return {
        **BROWSER_HEADERS,
        **session.headers,
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{BASE_URL}/",
    }


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
