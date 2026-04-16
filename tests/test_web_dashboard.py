"""Tests for src/monitoring/web_dashboard.py — Flask dashboard routes."""
import os
import sys
import time
from unittest.mock import patch, MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def flask_client():
    """Create a Flask test client for the web dashboard."""
    from src.monitoring.web_dashboard import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestDashboardRoute:
    def test_home_returns_200(self, flask_client):
        """The home page should return HTTP 200."""
        with patch('src.monitoring.web_dashboard.load_config', return_value={
            "gateway": {"name": "TestNode", "port": "COM3", "connection_type": "serial", "bitrate": 500},
            "dashboard": {"host": "127.0.0.1", "port": 5000},
        }), \
             patch('src.monitoring.web_dashboard.check_rns_lib', return_value=(True, "0.7.4")), \
             patch('src.monitoring.web_dashboard.check_meshtastic_lib', return_value=(True, "2.3.0")), \
             patch('src.monitoring.web_dashboard.check_serial_ports', return_value=["/dev/ttyUSB0"]), \
             patch('src.monitoring.web_dashboard.check_rnsd_status', return_value=(True, "PID 1234")), \
             patch('src.monitoring.web_dashboard.check_meshtasticd_status', return_value=(True, "active")), \
             patch('src.monitoring.web_dashboard.check_rns_udp_port', return_value=(True, "in use")):

            response = flask_client.get('/')
            assert response.status_code == 200

    def test_home_contains_version(self, flask_client):
        """The home page should display the version string."""
        with patch('src.monitoring.web_dashboard.load_config', return_value={}), \
             patch('src.monitoring.web_dashboard.check_rns_lib', return_value=(False, "not installed")), \
             patch('src.monitoring.web_dashboard.check_meshtastic_lib', return_value=(False, "not installed")), \
             patch('src.monitoring.web_dashboard.check_serial_ports', return_value=["(none)"]), \
             patch('src.monitoring.web_dashboard.check_rnsd_status', return_value=(False, "not running")), \
             patch('src.monitoring.web_dashboard.check_meshtasticd_status', return_value=(False, "not running")), \
             patch('src.monitoring.web_dashboard.check_rns_udp_port', return_value=(False, "not in use")):

            response = flask_client.get('/')
            assert response.status_code == 200
            assert b'SUPERVISOR NOC' in response.data

    def test_home_missing_config(self, flask_client):
        """Dashboard should still render when config is missing."""
        with patch('src.monitoring.web_dashboard.load_config', return_value={}), \
             patch('src.monitoring.web_dashboard.check_rns_lib', return_value=(False, "not installed")), \
             patch('src.monitoring.web_dashboard.check_meshtastic_lib', return_value=(False, "not installed")), \
             patch('src.monitoring.web_dashboard.check_serial_ports', return_value=["(none)"]), \
             patch('src.monitoring.web_dashboard.check_rnsd_status', return_value=(False, "not running")), \
             patch('src.monitoring.web_dashboard.check_meshtasticd_status', return_value=(False, "not running")), \
             patch('src.monitoring.web_dashboard.check_rns_udp_port', return_value=(False, "not in use")):

            response = flask_client.get('/')
            assert response.status_code == 200
            # Should show the "not found" message
            assert b'config.json not found' in response.data

    def test_home_shows_library_status(self, flask_client):
        """Dashboard should display library availability."""
        with patch('src.monitoring.web_dashboard.load_config', return_value={}), \
             patch('src.monitoring.web_dashboard.check_rns_lib', return_value=(True, "0.8.0")), \
             patch('src.monitoring.web_dashboard.check_meshtastic_lib', return_value=(True, "2.4.0")), \
             patch('src.monitoring.web_dashboard.check_serial_ports', return_value=["/dev/ttyACM0"]), \
             patch('src.monitoring.web_dashboard.check_rnsd_status', return_value=(True, "PID 999")), \
             patch('src.monitoring.web_dashboard.check_meshtasticd_status', return_value=(True, "active")), \
             patch('src.monitoring.web_dashboard.check_rns_udp_port', return_value=(True, "in use")):

            response = flask_client.get('/')
            assert b'0.8.0' in response.data
            assert b'2.4.0' in response.data


class TestSecurityHeaders:
    """Verify OWASP security headers are present on all responses."""

    def _mock_all_checks(self):
        """Return a context manager that mocks all service check calls."""
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch('src.monitoring.web_dashboard.load_config', return_value={}))
        stack.enter_context(patch('src.monitoring.web_dashboard.check_rns_lib', return_value=(False, "n/a")))
        stack.enter_context(patch('src.monitoring.web_dashboard.check_meshtastic_lib', return_value=(False, "n/a")))
        stack.enter_context(patch('src.monitoring.web_dashboard.check_serial_ports', return_value=[]))
        stack.enter_context(patch('src.monitoring.web_dashboard.check_rnsd_status', return_value=(False, "n/a")))
        stack.enter_context(patch('src.monitoring.web_dashboard.check_meshtasticd_status', return_value=(False, "n/a")))
        stack.enter_context(patch('src.monitoring.web_dashboard.check_rns_udp_port', return_value=(False, "n/a")))
        return stack

    def test_csp_header_present(self, flask_client):
        """Content-Security-Policy header should be set."""
        with self._mock_all_checks():
            response = flask_client.get('/')
            assert 'Content-Security-Policy' in response.headers
            assert "default-src 'self'" in response.headers['Content-Security-Policy']

    def test_x_content_type_options_header(self, flask_client):
        """X-Content-Type-Options: nosniff should be set."""
        with self._mock_all_checks():
            response = flask_client.get('/')
            assert response.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_x_frame_options_header(self, flask_client):
        """X-Frame-Options: DENY should be set."""
        with self._mock_all_checks():
            response = flask_client.get('/')
            assert response.headers.get('X-Frame-Options') == 'DENY'


class TestDashboardContent:
    """Verify dashboard template renders expected data."""

    def test_config_values_in_html(self, flask_client):
        """Dashboard should display gateway config values."""
        with patch('src.monitoring.web_dashboard.load_config', return_value={
            "gateway": {"name": "MyTestNode", "port": "/dev/ttyACM0",
                        "connection_type": "serial", "bitrate": 500},
        }), \
             patch('src.monitoring.web_dashboard.check_rns_lib', return_value=(True, "0.7.4")), \
             patch('src.monitoring.web_dashboard.check_meshtastic_lib', return_value=(True, "2.3.0")), \
             patch('src.monitoring.web_dashboard.check_serial_ports', return_value=["/dev/ttyACM0"]), \
             patch('src.monitoring.web_dashboard.check_rnsd_status', return_value=(False, "not running")), \
             patch('src.monitoring.web_dashboard.check_meshtasticd_status', return_value=(False, "not running")), \
             patch('src.monitoring.web_dashboard.check_rns_udp_port', return_value=(False, "not in use")):

            response = flask_client.get('/')
            assert b'MyTestNode' in response.data
            assert b'/dev/ttyACM0' in response.data

    def test_404_response(self, flask_client):
        """Non-existent routes should return 404."""
        response = flask_client.get('/nonexistent')
        assert response.status_code == 404


class TestApiRateLimiting:
    """`/api/*` endpoints throttle bursty callers to RATE_LIMIT_MAX_REQUESTS
    per RATE_LIMIT_WINDOW per remote IP."""

    @pytest.fixture(autouse=True)
    def _reset_buckets(self):
        from src.monitoring import web_dashboard
        web_dashboard._reset_rate_limits()
        yield
        web_dashboard._reset_rate_limits()

    def test_under_limit_allowed(self, flask_client):
        from src.monitoring import web_dashboard
        web_dashboard._bridge_health_ref = None  # 503 path is fine
        for _ in range(5):
            r = flask_client.get('/api/health')
            assert r.status_code in (200, 503)

    def test_over_limit_returns_429(self, flask_client):
        from src.monitoring import web_dashboard
        # The decorator captured RATE_LIMIT_MAX_REQUESTS at import time, so
        # seed the bucket with that many timestamps to simulate exhaustion.
        ip = "127.0.0.1"
        with web_dashboard._rate_lock:
            bucket = web_dashboard._rate_buckets[(ip, "api_health")]
            now = time.monotonic()
            for _ in range(web_dashboard.RATE_LIMIT_MAX_REQUESTS):
                bucket.append(now)

        r = flask_client.get('/api/health')
        assert r.status_code == 429
        assert r.json["error"] == "rate limit exceeded"
        assert "Retry-After" in r.headers

    def test_per_endpoint_buckets_are_independent(self, flask_client):
        from src.monitoring import web_dashboard
        ip = "127.0.0.1"
        # Saturate /api/health bucket only.
        with web_dashboard._rate_lock:
            now = time.monotonic()
            for _ in range(web_dashboard.RATE_LIMIT_MAX_REQUESTS):
                web_dashboard._rate_buckets[(ip, "api_health")].append(now)
        # /api/messages must still be reachable.
        r = flask_client.get('/api/messages')
        assert r.status_code == 200
