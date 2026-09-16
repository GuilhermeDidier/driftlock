# The pipeline reads the demo storefront from this same server over HTTP.
# With gunicorn's default (one sync worker, no threads) the run request holds
# the only worker while it waits on /demo/store/, which can never be served:
# every run dies on a 20s ReadTimeout. Threads leave room for that fetch.
workers = 1
threads = 4
# A run that heals waits on the model for a few seconds on top of the fetch.
timeout = 120
