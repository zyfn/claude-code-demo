"""Entry point."""

import asyncio
from src.config import Config
from src.repl import repl_loop


def main():
    asyncio.run(repl_loop(Config()))


if __name__ == "__main__":
    main()
