"""Code Relay command line and double-click entrypoint."""
import argparse
import json
from pathlib import Path

from . import __version__


def main():
    parser = argparse.ArgumentParser(description="Code Relay: host-led delegation to your API models.")
    parser.add_argument("command", nargs="?", choices=["serve", "status", "setup", "install", "self-test"], default="setup")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--state-dir", type=Path)
    args = parser.parse_args()
    if args.command == "serve":
        from .server import serve
        serve(args.config, args.state_dir)
    elif args.command == "setup":
        from .gui import main as setup
        from .installer import install
        setup(install_callback=install)
    elif args.command == "install":
        from .installer import install
        print(json.dumps(install(), indent=2))
    elif args.command == "self-test":
        from .selftest import run
        print(json.dumps(run(), indent=2))
    else:
        from .server import Server
        print(json.dumps(Server(configuration=args.config, state_dir=args.state_dir).get_relay().status(), indent=2))


if __name__ == "__main__":
    main()
