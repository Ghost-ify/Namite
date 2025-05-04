"""
Roblox API integration for checking username availability.
This file contains functions to interact with the Roblox API.
"""
import asyncio
import aiohttp
import logging
import time
from typing import Tuple, Optional, Dict

logger = logging.getLogger('roblox_username_bot')

# Roblox API endpoint for username validation
ROBLOX_USERNAME_API = "https://auth.roblox.com/v1/usernames/validate"

# Global session for reuse across requests
_session: Optional[aiohttp.ClientSession] = None

# Cache of recently checked usernames to avoid duplicate API calls
username_cache: Dict[str, Tuple[bool, int, str, float]] = {}
CACHE_EXPIRY = 300  # 5 minutes in seconds

async def get_session() -> aiohttp.ClientSession:
    """
    Get or create a global aiohttp session.
    Using a single session for multiple requests is more efficient.
    """
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5),  # 5 second timeout
            headers={
                "User-Agent": "RobloxUsernameChecker/1.0",
                "Accept": "application/json"
            }
        )
    return _session

async def check_username_availability(username: str) -> Tuple[bool, int, str]:
    """
    Check if a Roblox username is available using the Roblox API.
    
    Args:
        username (str): The username to check
        
    Returns:
        Tuple[bool, int, str]: A tuple containing:
            - Boolean indicating if the username is available
            - Status code from the API
            - Message or reason for availability status
    """
    # Check cache first to avoid duplicate API calls
    current_time = time.time()
    if username in username_cache:
        is_available, status_code, message, timestamp = username_cache[username]
        if current_time - timestamp < CACHE_EXPIRY:
            return is_available, status_code, message
    
    params = {"request.username": username}
    
    # Maximum number of retries for transient errors
    max_retries = 2  # Reduced from 3 to 2 for faster operation
    retry_delay = 1  # Reduced from 2 to 1 second
    
    for attempt in range(max_retries):
        try:
            session = await get_session()
            async with session.get(ROBLOX_USERNAME_API, params=params) as response:
                # Parse the JSON response
                data = await response.json()
                
                # Check the status code
                if response.status == 200:
                    # According to the requirements, code 0 means available
                    if 'code' in data and data['code'] == 0:
                        result = (True, response.status, "Username is available")
                        username_cache[username] = (*result, current_time)
                        return result
                    else:
                        code = data.get('code', 'unknown')
                        message = data.get('message', 'Unknown reason')
                        result = (False, response.status, f"Code: {code}, Message: {message}")
                        username_cache[username] = (*result, current_time)
                        return result
                elif response.status == 429:
                    # Rate limited, wait briefly before retrying
                    logger.warning(f"Rate limited by Roblox API. Attempt {attempt+1}/{max_retries}")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    result = (False, response.status, f"API Error: HTTP {response.status}")
                    username_cache[username] = (*result, current_time)
                    return result
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error checking username '{username}': {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                return False, 0, f"Network error: {str(e)}"
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout checking username '{username}'")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                return False, 0, "Request timed out"
                
        except Exception as e:
            logger.error(f"Unexpected error checking username '{username}': {str(e)}")
            return False, 0, f"Unexpected error: {str(e)}"
    
    # If we've exhausted all retries
    return False, 0, "Failed after maximum retries"

# Clean up old cache entries periodically
async def clean_cache():
    """Remove expired entries from the username cache."""
    current_time = time.time()
    expired_keys = [k for k, (_, _, _, t) in username_cache.items() 
                   if current_time - t >= CACHE_EXPIRY]
    for k in expired_keys:
        del username_cache[k]
