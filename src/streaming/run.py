"""Run the streaming pipeline independently of the existing batch main flow."""

from .consumer import main


def run_streaming():
    main()


if __name__ == "__main__":
    run_streaming()
