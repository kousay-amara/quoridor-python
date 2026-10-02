import os


def pytest_sessionstart(session):
    # Force an English locale for deterministic CLI output in tests.
    os.environ["LC_ALL"] = "C.UTF-8"
    os.environ["LANG"] = "C.UTF-8"
