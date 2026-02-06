"""
AWS Lambda handler for the Stock Track Record API.

This module wraps the FastAPI application with Mangum for Lambda compatibility.
"""
from mangum import Mangum
from app.main import app

# Create the Lambda handler
handler = Mangum(app, lifespan="off")
