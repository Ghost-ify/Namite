"""
Roblox API integration for checking username availability.
This file contains functions to interact with the Roblox API.
"""
import asyncio
import aiohttp
import logging
import time
from typing import Tuple, Optional, Dict, List, Any
from database import record_username_check, is_username_in_cooldown, get_username_status

logger = logging.getLogger('roblox_username_bot')

# Roblox API endpoint for username validation
ROBLOX_USERNAME_API = "https://auth.roblox.com/v1/usernames/validate"

# Global session for reuse across requests
_session: Optional[aiohttp.ClientSession] = None

# In-memory cache for very recent checks (to avoid hammering the database)
memory_cache: Dict[str, Tuple[bool, int, str, float]] = {}
MEMORY_CACHE_EXPIRY = 60  # 1 minute in seconds

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
    # Check in-memory cache first (very recent checks)
    current_time = time.time()
    if username in memory_cache:
        is_available, status_code, message, timestamp = memory_cache[username]
        if current_time - timestamp < MEMORY_CACHE_EXPIRY:
            return is_available, status_code, message
    
    # Check if this username is in cooldown (was checked in the last 3 days)
    if is_username_in_cooldown(username):
        # Return the stored result from the database
        status = get_username_status(username)
        if status:
            logger.info(f"Username '{username}' in cooldown, returning cached result")
            return status['is_available'], status['status_code'], status['message']
    
    # Proceed with API check
    params = {"request.username": username}
    
    # Maximum number of retries for transient errors
    max_retries = 1
    retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            session = await get_session()
            async with session.get(ROBLOX_USERNAME_API, params=params) as response:
                # Parse the JSON response
                data = await response.json()
                
                # Check the status code
                if response.status == 200:
                    # According to the requirements, code 0 means available
                    is_available = False
                    status_code = response.status
                    message = ""
                    
                    if 'code' in data and data['code'] == 0:
                        is_available = True
                        message = "Username is available"
                    else:
                        code = data.get('code', 'unknown')
                        message = data.get('message', 'Unknown reason')
                        message = f"Code: {code}, Message: {message}"
                    
                    # Store result in database
                    record_username_check(username, is_available, status_code, message)
                    
                    # Store in memory cache
                    memory_cache[username] = (is_available, status_code, message, current_time)
                    
                    return is_available, status_code, message
                elif response.status == 429:
                    # Rate limited, wait briefly before retrying
                    logger.warning(f"Rate limited by Roblox API. Attempt {attempt+1}/{max_retries}")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    message = f"API Error: HTTP {response.status}"
                    
                    # Store failed result
                    record_username_check(username, False, response.status, message)
                    memory_cache[username] = (False, response.status, message, current_time)
                    
                    return False, response.status, message
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error checking username '{username}': {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                message = f"Network error: {str(e)}"
                record_username_check(username, False, 0, message)
                return False, 0, message
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout checking username '{username}'")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                message = "Request timed out"
                record_username_check(username, False, 0, message)
                return False, 0, message
                
        except Exception as e:
            logger.error(f"Unexpected error checking username '{username}': {str(e)}")
            message = f"Unexpected error: {str(e)}"
            record_username_check(username, False, 0, message)
            return False, 0, message
    
    # If we've exhausted all retries
    message = "Failed after maximum retries"
    record_username_check(username, False, 0, message)
    return False, 0, message

# Clean up old memory cache entries periodically
async def clean_memory_cache():
    """Remove expired entries from the in-memory cache."""
    current_time = time.time()
    expired_keys = [k for k, (_, _, _, t) in memory_cache.items() 
                   if current_time - t >= MEMORY_CACHE_EXPIRY]
    for k in expired_keys:
        del memory_cache[k]
