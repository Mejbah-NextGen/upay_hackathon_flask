"""Gunicorn entry point; configuration errors stop startup before serving."""

from app import create_app
from config import ProductionConfig

app = create_app(ProductionConfig)
