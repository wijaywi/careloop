"""Run CareLoop with ``python -m api``."""

import argparse

from .app import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline CareLoop API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
