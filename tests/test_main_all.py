import importlib
from unittest.mock import Mock

import pytest


def launcher():
    return importlib.import_module('main_all')


def test_failed_frontend_start_stops_backend(monkeypatch):
    app = launcher()
    backend = Mock()
    backend.poll.return_value = None
    spawn = Mock(side_effect=[backend, OSError('frontend failed')])
    stop = Mock()
    monkeypatch.setattr(app.subprocess, 'Popen', spawn)
    monkeypatch.setattr(app, 'stop_process', stop)
    with pytest.raises(OSError, match='frontend failed'):
        app.run_services([['backend'], ['frontend']], app.ROOT, {})
    stop.assert_called_once_with(backend)


def test_service_exit_stops_peer_and_returns_failure(monkeypatch):
    app = launcher()
    backend, frontend = Mock(), Mock()
    backend.poll.return_value = 3
    frontend.poll.return_value = None
    monkeypatch.setattr(app.subprocess, 'Popen', Mock(side_effect=[backend, frontend]))
    stop = Mock()
    monkeypatch.setattr(app, 'stop_process', stop)
    assert app.run_services([['backend'], ['frontend']], app.ROOT, {}) == 3
    assert [call.args[0] for call in stop.call_args_list] == [frontend, backend]


def test_occupied_port_fails_without_stopping_existing_service():
    import socket
    app = launcher()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        with pytest.raises(RuntimeError, match='already in use'):
            app.check_port(listener.getsockname()[1])


def test_python_executable_prefers_project_environment():
    app = launcher()
    expected = app.ROOT / '.venv' / 'Scripts' / 'python.exe'
    if expected.is_file():
        assert app.python_executable() == str(expected)
