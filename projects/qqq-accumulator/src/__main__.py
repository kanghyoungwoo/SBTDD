"""Command line entry point: python -m src --config PATH <command> ..."""
import sys

from src.app import main

sys.exit(main(sys.argv[1:]))
