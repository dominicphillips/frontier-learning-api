import argparse
import importlib
from pathlib import Path


def serve() -> None:
    parser = argparse.ArgumentParser(prog="frontier-learning-api")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    import uvicorn

    from .app import create_app

    uvicorn.run(
        create_app(args.data_dir),
        host=args.host,
        port=args.port,
        log_level="info",
        server_header=False,
        proxy_headers=False,
    )


def collect() -> None:
    parser = argparse.ArgumentParser(prog="frontier-learning-collect", add_help=False)
    parser.add_argument("--provider", choices=["openai", "claude", "gemini"], required=True)
    args, remaining = parser.parse_known_args()
    module = importlib.import_module(f"frontier_learning.providers.{args.provider}.cli")
    if "--snapshot" not in remaining:
        remaining = ["--snapshot", f"data/{args.provider}.json", *remaining]
    if "--state-dir" not in remaining:
        remaining = ["--state-dir", f"data/collector/{args.provider}", *remaining]
    module.collect(remaining)
