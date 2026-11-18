"""Default entry point for the shared A2 streaming and scheduled batch service."""

from a2.runtime import main


def run_streaming():
    main()


if __name__ == "__main__":
    run_streaming()
