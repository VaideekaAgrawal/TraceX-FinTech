"""
TraceX API - redirects to v3 microservice server.
Run with: uvicorn api.server:app --reload --port 8000
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.server_v3 import app  # noqa: F401
