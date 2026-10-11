import argparse

import uvicorn

from learnmarks.core.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="learnmarks")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the local web app")
    serve.add_argument("--reload", action="store_true", help="restart on code changes (development)")
    args = parser.parse_args()

    if args.cmd == "serve":
        # Always loopback: the app is never exposed to the network (DESIGN §10).
        uvicorn.run("learnmarks.main:create_app", factory=True, host="127.0.0.1", port=settings.port,
                    reload=args.reload)


if __name__ == "__main__":
    main()
