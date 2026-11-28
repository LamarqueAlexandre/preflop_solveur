"""Run the API: ``uv run python -m api [--host H] [--port P] [--reload]``."""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m api", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="restart on code changes")
    args = parser.parse_args()
    uvicorn.run(
        "api.app:app_from_env", factory=True, host=args.host, port=args.port, reload=args.reload
    )


if __name__ == "__main__":
    main()
