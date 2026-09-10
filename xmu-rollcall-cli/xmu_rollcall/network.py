"""Network failure classification shared by monitoring and API calls."""
import requests

REQUEST_TIMEOUT = (10, 30)
RETRY_INITIAL_DELAY = 5
RETRY_MAX_DELAY = 60
RETRY_MAX_ATTEMPTS = 10


def is_retryable(exc):
    # Certificate/configuration errors need operator attention.
    if isinstance(exc, requests.exceptions.SSLError):
        return False
    if isinstance(exc, (requests.ConnectionError, requests.Timeout,
                        requests.exceptions.ChunkedEncodingError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in (408, 429, 500, 502, 503, 504)
    return False
