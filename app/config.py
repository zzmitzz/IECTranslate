import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_KEY_HEADER_NAME = "x-api-key"
DEFAULT_API_KEY = "change-me"
API_KEY = os.getenv("API_KEY", DEFAULT_API_KEY)

# Debug: Print what API key was loaded (first 8 chars for security)
if API_KEY:
    print(f"API Key loaded: {API_KEY[:8]}...")
else:
    print("No API Key found!")

