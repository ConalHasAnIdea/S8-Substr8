from pathlib import Path

from discovery.mock_discovery_engine import run_discovery


if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    run_discovery(base / "data", base / "output")
