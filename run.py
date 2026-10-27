"""Start the app:  python run.py [port]"""
import sys

from app.server import main

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
