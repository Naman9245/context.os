"""`contextos` command line."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="contextos")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the API (and the built frontend, if present)")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--reload", action="store_true", help="auto-reload on code changes")

    sub.add_parser("init-db", help="create the database tables")

    args = parser.parse_args(argv)

    if args.command == "serve":
        import uvicorn

        from contextos.config import get_settings

        settings = get_settings()
        uvicorn.run(
            "contextos.main:app",
            host=args.host or settings.host,
            port=args.port or settings.port,
            reload=args.reload,
        )
    elif args.command == "init-db":
        from contextos.db import get_engine, init_db

        init_db()
        print(f"database ready: {get_engine().url}")


if __name__ == "__main__":
    main()
