"""Enables `python -m prototype_api` -- runs the FastAPI app locally via uvicorn.
Run from evals/gate0/ (see README.md). Development only: single worker, auto-reload off, no TLS.
"""
import uvicorn


def main() -> None:
    uvicorn.run("prototype_api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
