"""
Tests fuer den Enhanced Retry-Decorator mit Error Classification.

Testet:
- Error Classification (classify_error): transient vs. permanent, Kategorien
- BinanceAPIError: Strukturierter Fehler-Wrapper mit Metadaten
- Retry-After Header Respektierung fuer 429 Responses
- Decorator-Verhalten: Retries bei transient, sofortiger Abbruch bei permanent
- Backward-Compatibility: _is_retryable() Wrapper
"""

from unittest.mock import MagicMock, patch

import pytest
import requests
from binance.exceptions import BinanceAPIException

from app.utils.retry import (
    BinanceAPIError,
    ErrorClassification,
    classify_error,
    _is_retryable,
    retry_on_transient_error,
)


# ============================================================
# Helpers: Mock-Objekte fuer BinanceAPIException
# ============================================================


def _make_binance_exc(status_code: int, retry_after: str = None) -> BinanceAPIException:
    """Erzeugt eine BinanceAPIException mit optionalem Retry-After Header."""
    response = MagicMock()
    response.status_code = status_code
    response.text = f'{{"code": -{status_code}, "msg": "Error {status_code}"}}'
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    response.headers = headers
    return BinanceAPIException(response, status_code, response.text)


def _make_http_error(status_code: int, retry_after: str = None) -> requests.exceptions.HTTPError:
    """Erzeugt eine requests.exceptions.HTTPError mit optionalem Retry-After Header."""
    response = MagicMock()
    response.status_code = status_code
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    response.headers = headers
    return requests.exceptions.HTTPError(response=response)


# ============================================================
# Tests: classify_error — Error Classification
# ============================================================


class TestClassifyError:
    """Testet die classify_error() Funktion fuer alle Error-Kategorien."""

    # --- BinanceAPIException ---

    def test_binance_429_is_transient_rate_limit(self):
        exc = _make_binance_exc(429)
        result = classify_error(exc)
        assert result.is_transient is True
        assert result.category == "rate_limit"
        assert result.status_code == 429

    def test_binance_500_is_transient_server_error(self):
        exc = _make_binance_exc(500)
        result = classify_error(exc)
        assert result.is_transient is True
        assert result.category == "server_error"
        assert result.status_code == 500

    def test_binance_502_is_transient_server_error(self):
        exc = _make_binance_exc(502)
        result = classify_error(exc)
        assert result.is_transient is True
        assert result.category == "server_error"
        assert result.status_code == 502

    def test_binance_400_is_permanent_client_error(self):
        exc = _make_binance_exc(400)
        result = classify_error(exc)
        assert result.is_transient is False
        assert result.category == "client_error"
        assert result.status_code == 400

    def test_binance_401_is_permanent_client_error(self):
        exc = _make_binance_exc(401)
        result = classify_error(exc)
        assert result.is_transient is False
        assert result.category == "client_error"
        assert result.status_code == 401

    def test_binance_403_is_permanent_client_error(self):
        exc = _make_binance_exc(403)
        result = classify_error(exc)
        assert result.is_transient is False
        assert result.category == "client_error"
        assert result.status_code == 403

    # --- Retry-After Header ---

    def test_binance_429_with_retry_after_header(self):
        exc = _make_binance_exc(429, retry_after="5")
        result = classify_error(exc)
        assert result.is_transient is True
        assert result.category == "rate_limit"
        assert result.retry_after == 5.0

    def test_binance_429_without_retry_after(self):
        exc = _make_binance_exc(429)
        result = classify_error(exc)
        assert result.retry_after is None

    # --- requests.exceptions ---

    def test_timeout_is_transient(self):
        exc = requests.exceptions.Timeout("Connection timed out")
        result = classify_error(exc)
        assert result.is_transient is True
        assert result.category == "timeout"
        assert result.status_code is None

    def test_connection_error_is_transient(self):
        exc = requests.exceptions.ConnectionError("Connection refused")
        result = classify_error(exc)
        assert result.is_transient is True
        assert result.category == "connection_error"
        assert result.status_code is None

    # --- HTTPError ---

    def test_http_error_429_is_transient_rate_limit(self):
        exc = _make_http_error(429)
        result = classify_error(exc)
        assert result.is_transient is True
        assert result.category == "rate_limit"
        assert result.status_code == 429

    def test_http_error_429_with_retry_after(self):
        exc = _make_http_error(429, retry_after="10")
        result = classify_error(exc)
        assert result.is_transient is True
        assert result.retry_after == 10.0

    def test_http_error_503_is_transient_server_error(self):
        exc = _make_http_error(503)
        result = classify_error(exc)
        assert result.is_transient is True
        assert result.category == "server_error"
        assert result.status_code == 503

    def test_http_error_400_is_permanent_client_error(self):
        exc = _make_http_error(400)
        result = classify_error(exc)
        assert result.is_transient is False
        assert result.category == "client_error"
        assert result.status_code == 400

    # --- Unknown Errors ---

    def test_value_error_is_permanent_unknown(self):
        exc = ValueError("bad input")
        result = classify_error(exc)
        assert result.is_transient is False
        assert result.category == "unknown"
        assert result.status_code is None
        assert result.retry_after is None

    def test_runtime_error_is_permanent_unknown(self):
        exc = RuntimeError("something broke")
        result = classify_error(exc)
        assert result.is_transient is False
        assert result.category == "unknown"


# ============================================================
# Tests: ErrorClassification Dataclass
# ============================================================


class TestErrorClassification:
    """Testet die ErrorClassification Dataclass."""

    def test_defaults(self):
        ec = ErrorClassification(is_transient=True, category="rate_limit")
        assert ec.status_code is None
        assert ec.retry_after is None

    def test_full_construction(self):
        ec = ErrorClassification(
            is_transient=True,
            category="rate_limit",
            status_code=429,
            retry_after=5.0,
        )
        assert ec.is_transient is True
        assert ec.category == "rate_limit"
        assert ec.status_code == 429
        assert ec.retry_after == 5.0


# ============================================================
# Tests: BinanceAPIError
# ============================================================


class TestBinanceAPIError:
    """Testet die BinanceAPIError Exception."""

    def test_creation_and_attributes(self):
        original = _make_binance_exc(429)
        classification = ErrorClassification(
            is_transient=True, category="rate_limit", status_code=429
        )
        err = BinanceAPIError(
            message="Rate limited",
            original_exception=original,
            classification=classification,
            attempts=3,
        )
        assert err.message == "Rate limited"
        assert err.original_exception is original
        assert err.classification is classification
        assert err.attempts == 3

    def test_str_representation(self):
        classification = ErrorClassification(
            is_transient=True, category="rate_limit", status_code=429
        )
        err = BinanceAPIError(
            message="Rate limited",
            original_exception=Exception("orig"),
            classification=classification,
            attempts=3,
        )
        s = str(err)
        assert "rate_limit" in s
        assert "Rate limited" in s
        assert "attempts=3" in s
        assert "status=429" in s

    def test_is_exception_subclass(self):
        classification = ErrorClassification(is_transient=False, category="client_error")
        err = BinanceAPIError(
            message="Bad request",
            original_exception=Exception(),
            classification=classification,
            attempts=1,
        )
        assert isinstance(err, Exception)


# ============================================================
# Tests: _is_retryable Backward Compatibility
# ============================================================


class TestIsRetryableBackwardCompat:
    """Testet dass _is_retryable() als Wrapper fuer classify_error() funktioniert."""

    def test_transient_returns_true(self):
        exc = _make_binance_exc(429)
        assert _is_retryable(exc) is True

    def test_permanent_returns_false(self):
        exc = _make_binance_exc(400)
        assert _is_retryable(exc) is False

    def test_timeout_returns_true(self):
        exc = requests.exceptions.Timeout()
        assert _is_retryable(exc) is True

    def test_unknown_returns_false(self):
        exc = ValueError("nope")
        assert _is_retryable(exc) is False


# ============================================================
# Tests: retry_on_transient_error Decorator
# ============================================================


class TestRetryDecorator:
    """Testet den retry_on_transient_error Decorator."""

    @patch("app.utils.retry.time.sleep")
    def test_transient_error_then_success(self, mock_sleep):
        """Transient error auf erstem Call, Erfolg auf zweitem -> kein Fehler."""
        call_count = 0

        @retry_on_transient_error(max_retries=3, base_delay=1.0)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _make_binance_exc(429)
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 2
        mock_sleep.assert_called_once()

    @patch("app.utils.retry.time.sleep")
    def test_permanent_error_raises_immediately(self, mock_sleep):
        """Permanent error (400) -> sofort BinanceAPIError, kein Retry."""
        call_count = 0

        @retry_on_transient_error(max_retries=3, base_delay=1.0)
        def bad_func():
            nonlocal call_count
            call_count += 1
            raise _make_binance_exc(400)

        with pytest.raises(BinanceAPIError) as exc_info:
            bad_func()

        assert call_count == 1
        assert exc_info.value.attempts == 1
        assert exc_info.value.classification.category == "client_error"
        assert exc_info.value.classification.is_transient is False
        mock_sleep.assert_not_called()

    @patch("app.utils.retry.time.sleep")
    def test_retries_exhausted_raises_binance_api_error(self, mock_sleep):
        """Transient error erschoepft max_retries -> BinanceAPIError mit attempts."""

        @retry_on_transient_error(max_retries=2, base_delay=1.0)
        def always_fails():
            raise _make_binance_exc(429)

        with pytest.raises(BinanceAPIError) as exc_info:
            always_fails()

        assert exc_info.value.attempts == 3  # 1 initial + 2 retries
        assert exc_info.value.classification.category == "rate_limit"
        assert exc_info.value.classification.is_transient is True

    @patch("app.utils.retry.time.sleep")
    def test_429_with_retry_after_uses_header_as_minimum(self, mock_sleep):
        """429 mit Retry-After=10 und base_delay=1 -> wartet mindestens 10s."""

        @retry_on_transient_error(max_retries=1, base_delay=1.0, max_delay=30.0)
        def rate_limited():
            raise _make_binance_exc(429, retry_after="10")

        with pytest.raises(BinanceAPIError):
            rate_limited()

        # Erster Retry: base_delay * 2^0 = 1.0, aber Retry-After=10 -> wartet >= 10
        assert mock_sleep.call_count == 1
        actual_delay = mock_sleep.call_args[0][0]
        assert actual_delay >= 10.0, f"Expected delay >= 10.0, got {actual_delay}"

    @patch("app.utils.retry.time.sleep")
    def test_timeout_is_retried(self, mock_sleep):
        """requests.Timeout wird retried."""
        call_count = 0

        @retry_on_transient_error(max_retries=2, base_delay=1.0)
        def timeout_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise requests.exceptions.Timeout("timed out")
            return "ok"

        result = timeout_then_ok()
        assert result == "ok"
        assert call_count == 2

    @patch("app.utils.retry.time.sleep")
    def test_connection_error_is_retried(self, mock_sleep):
        """requests.ConnectionError wird retried."""
        call_count = 0

        @retry_on_transient_error(max_retries=2, base_delay=1.0)
        def conn_err_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise requests.exceptions.ConnectionError("refused")
            return "ok"

        result = conn_err_then_ok()
        assert result == "ok"
        assert call_count == 2

    @patch("app.utils.retry.time.sleep")
    def test_unknown_error_raises_binance_api_error(self, mock_sleep):
        """Unbekannter Fehler (ValueError) -> sofort BinanceAPIError, kein Retry."""
        call_count = 0

        @retry_on_transient_error(max_retries=3, base_delay=1.0)
        def unknown_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("unexpected")

        with pytest.raises(BinanceAPIError) as exc_info:
            unknown_fail()

        assert call_count == 1
        assert exc_info.value.classification.category == "unknown"
        mock_sleep.assert_not_called()

    @patch("app.utils.retry.time.sleep")
    def test_exponential_backoff_timing(self, mock_sleep):
        """Backoff verdoppelt sich mit jedem Retry (ohne Retry-After)."""
        attempt = 0

        @retry_on_transient_error(max_retries=3, base_delay=2.0, max_delay=100.0)
        def always_500():
            nonlocal attempt
            attempt += 1
            raise _make_binance_exc(500)

        with pytest.raises(BinanceAPIError):
            always_500()

        assert mock_sleep.call_count == 3
        # Delays: 2*2^0=2, 2*2^1=4, 2*2^2=8 (plus jitter)
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert delays[0] >= 2.0
        assert delays[0] < 2.0 * 1.3  # Max 25% jitter
        assert delays[1] >= 4.0
        assert delays[1] < 4.0 * 1.3
        assert delays[2] >= 8.0
        assert delays[2] < 8.0 * 1.3

    @patch("app.utils.retry.time.sleep")
    def test_max_delay_cap(self, mock_sleep):
        """Delay wird durch max_delay begrenzt."""

        @retry_on_transient_error(max_retries=1, base_delay=100.0, max_delay=5.0)
        def fail_once():
            raise _make_binance_exc(500)

        with pytest.raises(BinanceAPIError):
            fail_once()

        actual_delay = mock_sleep.call_args[0][0]
        # max_delay=5.0, so delay should be capped at 5.0 + jitter (max 25% of 5.0)
        assert actual_delay <= 5.0 * 1.3, f"Delay {actual_delay} exceeds max_delay cap"

    @patch("app.utils.retry.time.sleep")
    def test_decorator_signature_compatibility(self, mock_sleep):
        """Decorator funktioniert ohne Argumente (Default-Werte)."""

        @retry_on_transient_error()
        def simple_func():
            return 42

        assert simple_func() == 42
        mock_sleep.assert_not_called()

    @patch("app.utils.retry.time.sleep")
    def test_binance_api_error_wraps_original_exception(self, mock_sleep):
        """BinanceAPIError enthaelt die Original-Exception."""
        original = _make_binance_exc(400)

        @retry_on_transient_error(max_retries=1)
        def fail():
            raise original

        with pytest.raises(BinanceAPIError) as exc_info:
            fail()

        assert exc_info.value.original_exception is original

    @patch("app.utils.retry.time.sleep")
    def test_http_error_429_with_retry_after_respected(self, mock_sleep):
        """HTTPError 429 mit Retry-After Header wird respektiert."""

        @retry_on_transient_error(max_retries=1, base_delay=1.0)
        def http_rate_limited():
            raise _make_http_error(429, retry_after="7")

        with pytest.raises(BinanceAPIError):
            http_rate_limited()

        actual_delay = mock_sleep.call_args[0][0]
        assert actual_delay >= 7.0, f"Expected delay >= 7.0, got {actual_delay}"
