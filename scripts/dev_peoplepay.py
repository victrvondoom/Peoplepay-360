"""Run the core or core plus isolated CivicMesh; installs nothing automatically."""
import argparse
import os
import secrets
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def interpreter(folder):
    path = ROOT / folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not path.is_file():
        raise SystemExit(f"Missing {path}. Install the documented isolated environment first.")
    return str(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assistance", action="store_true")
    parser.add_argument("--all", action="store_true", help="All integrated runtime services; bundled specialist UIs still use their own commands")
    parser.add_argument("--gateway-port", type=int, default=8080)
    parser.add_argument("--echo-port", type=int, default=8090)
    parser.add_argument("--civicmesh-port", type=int, default=8092)
    args = parser.parse_args()
    args.assistance = args.assistance or args.all
    ports = [args.gateway_port, args.echo_port] + ([args.civicmesh_port] if args.assistance else [])
    if len(set(ports)) != len(ports) or any(not 1024 <= p <= 65535 for p in ports):
        raise SystemExit("Service ports must be distinct and between 1024 and 65535")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PEOPLEPAY_ECHO_URL"] = f"http://127.0.0.1:{args.echo_port}"
    commands = [(interpreter(".venv-echo"), "-m", "uvicorn", "echo.api:app", "--host", "127.0.0.1", "--port", str(args.echo_port)),
                (interpreter(".venv-journey-review"), "-m", "gateway.app")]
    env["BEACON_GATEWAY_PORT"] = str(args.gateway_port)
    if args.assistance:
        env["PEOPLEPAY_CIVICMESH_TOKEN"] = env.get("PEOPLEPAY_CIVICMESH_TOKEN") or secrets.token_urlsafe(48)
        env["PEOPLEPAY_CIVICMESH_API_URL"] = f"http://127.0.0.1:{args.civicmesh_port}"
        commands.insert(0, (interpreter(".venv-civicmesh"), "-m", "uvicorn", "extensions.civicmesh.service:app", "--host", "127.0.0.1", "--port", str(args.civicmesh_port)))
    children = []
    core_children = []
    optional_children = []
    try:
        for command in commands:
            child_env = env
            if "extensions.civicmesh.service:app" in command:
                permitted = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "USERPROFILE", "LANG", "LC_ALL", "PYTHONUTF8", "PEOPLEPAY_CIVICMESH_TOKEN", "CIVICMESH_POLICY_DATE"}
                child_env = {key: value for key, value in env.items() if key.upper() in permitted}
            child = subprocess.Popen(command, cwd=ROOT, env=child_env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            children.append(child)
            if "extensions.civicmesh.service:app" in command:
                optional_children.append(child)
            else:
                core_children.append(child)
        print(f"PeoplePay: http://127.0.0.1:{args.gateway_port}  Assistance: {'enabled' if args.assistance else 'not configured'}", flush=True)
        while all(child.poll() is None for child in core_children):
            for child in list(optional_children):
                if child.poll() is not None:
                    print("CivicMesh stopped. Core services continue; assistance reports provider unavailable. Restart the launcher to recover the provider.", flush=True)
                    optional_children.remove(child)
            time.sleep(0.5)
        raise SystemExit("A core service stopped; inspect its output. Remaining services are being stopped.")
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    main()
