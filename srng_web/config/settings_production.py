import os

from .settings import *

DEBUG = False
SECRET_KEY = os.environ["SRNG_SECRET_KEY"]

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
public_host = os.environ.get("SRNG_PUBLIC_HOST")
if public_host:
    ALLOWED_HOSTS.append(public_host)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
