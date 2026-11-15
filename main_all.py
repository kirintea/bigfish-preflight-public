"""Start the local API and Vite together; stop both when either exits."""

import argparse
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - uv installs the project dependencies
    load_dotenv = None


ROOT = Path(__file__).resolve().parent


def python_executable():
    """Use the project environment when launching the API child process."""
    candidates = [ROOT / '.venv' / 'Scripts' / 'python.exe',
                  ROOT / '.venv' / 'bin' / 'python']
    return str(next((path for path in candidates if path.is_file()), Path(sys.executable)))


def load_local_env():
    env_file = ROOT / '.env'
    if not env_file.is_file():
        return
    if load_dotenv:
        load_dotenv(env_file, override=False)
        return
    for raw in env_file.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        name, value = name.strip(), value.strip()
        if name and name not in os.environ:
            os.environ[name] = value.strip('"\'')


def check_port(port):
    with socket.socket() as probe:
        if os.name == 'nt':
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            raise RuntimeError(f'Port {port} is already in use; stop that service or choose another port.') from None


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # npm is launched through cmd.exe; CTRL_BREAK can leave an interactive
        # "Terminate batch job?" prompt and prevent the parent from exiting.
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return
        return
    else:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def run_services(commands, root, environment):
    processes = []
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    try:
        for command, directory in zip(commands, [root, root / 'webui']):
            processes.append(subprocess.Popen(command, cwd=directory, env=environment, **options))
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    print(f'Service exited ({code}); stopping both services.', flush=True)
                    return code or 1
            time.sleep(0.2)
    except KeyboardInterrupt:
        print('\nStopping both services...', flush=True)
        return 0
    finally:
        for process in reversed(processes):
            stop_process(process)


def main():
    parser = argparse.ArgumentParser(description='Start Bigfish API and WebUI together')
    parser.add_argument('--config', default='configs/test.yaml')
    parser.add_argument('--port', type=int, default=8091, help='API port')
    parser.add_argument('--frontend-port', type=int, default=5173)
    parser.add_argument('--real-agent', action='store_true',
                        help='enable the configured OpenAI-compatible model instead of offline replies')
    args = parser.parse_args()
    try:
        load_local_env()
        if not all(1 <= port <= 65535 for port in [args.port, args.frontend_port]):
            raise RuntimeError('Ports must be between 1 and 65535.')
        if args.port == args.frontend_port:
            raise RuntimeError('API and WebUI must use different ports.')
        for port in [args.port, args.frontend_port]:
            check_port(port)
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm:
            raise RuntimeError('npm was not found; install Node.js and reopen the terminal.')
        if not (ROOT / 'webui/node_modules/vite/bin/vite.js').is_file():
            raise RuntimeError('Frontend dependencies are missing; run: npm.cmd --prefix webui ci')
        environment = {**os.environ, 'BIGFISH_API': f'http://127.0.0.1:{args.port}', 'PYTHONUNBUFFERED': '1'}
        if args.real_agent:
            if not environment.get('LLM_API_KEY'):
                raise RuntimeError('--real-agent requires LLM_API_KEY in the environment or .env')
            environment['BIGFISH_OFFLINE_MODE'] = 'false'
        else:
            environment.setdefault('BIGFISH_OFFLINE_MODE', 'true')
        if not environment.get('TEST_ADMIN_TOKEN'):
            # This is a loopback-only test service credential; callers can override it.
            environment['TEST_ADMIN_TOKEN'] = 'local-npc-lab'
            print(f'Local NPC LAB credential: {environment["TEST_ADMIN_TOKEN"]}', flush=True)
        else:
            print('NPC LAB credential: using TEST_ADMIN_TOKEN from your environment.', flush=True)
        backend = [python_executable(), str(ROOT / 'main.py'), '--config', args.config,
                   '--host', '127.0.0.1', '--port', str(args.port)]
        frontend = [npm, 'run', 'dev', '--', '--port', str(args.frontend_port), '--strictPort']
        if os.name == 'nt':
            frontend = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c',
                        f'npm.cmd run dev -- --port {args.frontend_port} --strictPort']
        print(f'WebUI: http://127.0.0.1:{args.frontend_port}/prologue\n'
              f'API: http://127.0.0.1:{args.port}\nCtrl+C stops both services.', flush=True)
        return run_services([backend, frontend], ROOT, environment)
    except (OSError, RuntimeError) as exc:
        print(f'Startup failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
