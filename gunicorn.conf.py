import os
import subprocess
import sys

# The pipeline reads the demo storefront from this same server over HTTP.
# With gunicorn's default (one sync worker, no threads) the run request holds
# the only worker while it waits on /demo/store/, which can never be served:
# every run dies on a 20s ReadTimeout. Threads leave room for that fetch.
workers = 1
threads = 4
# A run that heals waits on the model for a few seconds on top of the fetch.
timeout = 120

# The public demo keeps its data in a SQLite file inside the instance, and an
# instance that restarts (a free one does, after sleeping) loses whatever it
# wrote since the deploy. Migrate and reseed before serving, so every start
# lands on the original storefront with no runs yet: that blank form is the
# demo's first screen. An explicit DATABASE_ENGINE on the host still wins.
os.environ.setdefault("DATABASE_ENGINE", "sqlite")


def on_starting(server):
    for command in (["migrate", "--noinput"], ["seed_demo"]):
        subprocess.run([sys.executable, "manage.py", *command], check=True)
