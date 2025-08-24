from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from typing import Optional
from ..config import API_KEY, API_KEY_HEADER_NAME

api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)

async def verify_api_key(api_key: Optional[str] = Depends(api_key_header)):
    if not api_key or api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "API-Key"},
        )
    return api_key