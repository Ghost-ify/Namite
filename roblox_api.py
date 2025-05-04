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

# Roblox API endpoints for username validation (with fallback)
API_ENDPOINTS = [
    {
        "url": "https://auth.roblox.com/v1/usernames/validate",
        "params": {"request.username": ""},
        "name": "Roblox Auth API",
        "delay": 0.5,  # Base delay between requests (will be adaptive)
        "rate_limit_count": 0,  # Count of 429 responses
        "last_request": 0,  # Timestamp of last request
        "success_streak": 0,  # Count of consecutive successful requests
        "enabled": True  # Whether this API is currently enabled
    },
    {
        "url": "https://users.roblox.com/v1/usernames/validate",
        "params": {"username": "", "type": "Username"},
        "name": "Roblox Users API",
        "delay": 0.5,  # Base delay between requests (will be adaptive)
        "rate_limit_count": 0,  # Count of 429 responses
        "last_request": 0,  # Timestamp of last request
        "success_streak": 0,  # Count of consecutive successful requests
        "enabled": True  # Whether this API is currently enabled
    }
]

# Default API to use (will rotate between endpoints)
current_api_index = 0

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

def update_api_delays():
    """Update API endpoint delays based on their rate limit history."""
    for endpoint in API_ENDPOINTS:
        # If we've hit rate limits, increase the delay
        if endpoint["rate_limit_count"] > 0:
            # Increase delay based on number of rate limits (max 5 seconds)
            endpoint["delay"] = min(5.0, 0.5 + (endpoint["rate_limit_count"] * 0.5))
            logger.info(f"Increased delay for {endpoint['name']} to {endpoint['delay']}s due to rate limits")
        
        # If we've had a good streak of successes, gradually decrease the delay
        elif endpoint["success_streak"] >= 10:
            # Decrease delay gradually (min 0.2 seconds)
            endpoint["delay"] = max(0.2, endpoint["delay"] - 0.1)
            endpoint["success_streak"] = 0  # Reset streak after adjusting
            logger.info(f"Decreased delay for {endpoint['name']} to {endpoint['delay']}s due to good performance")

def select_next_api():
    """Select the next API endpoint to use, favoring the one with better performance."""
    global current_api_index
    
    # Get the current time
    current_time = time.time()
    
    # Check if the current API is enabled
    if not API_ENDPOINTS[current_api_index]["enabled"]:
        # Find the next enabled API
        for i in range(len(API_ENDPOINTS)):
            next_index = (current_api_index + i) % len(API_ENDPOINTS)
            if API_ENDPOINTS[next_index]["enabled"]:
                current_api_index = next_index
                break
        else:
            # If no APIs are enabled, enable the first one as a fallback
            logger.warning("No APIs are enabled! Re-enabling the primary API.")
            API_ENDPOINTS[0]["enabled"] = True
            current_api_index = 0
    
    # Check if we need to enforce a delay for the current endpoint
    current_endpoint = API_ENDPOINTS[current_api_index]
    elapsed = current_time - current_endpoint["last_request"]
    
    # If enough time has passed since the last request, use the same endpoint
    if elapsed >= current_endpoint["delay"]:
        return current_api_index
    
    # Otherwise, try to find an alternative enabled endpoint
    for i in range(1, len(API_ENDPOINTS)):
        alt_index = (current_api_index + i) % len(API_ENDPOINTS)
        alt_endpoint = API_ENDPOINTS[alt_index]
        
        # Skip disabled endpoints
        if not alt_endpoint["enabled"]:
            continue
            
        elapsed = current_time - alt_endpoint["last_request"]
        
        # If this alternative endpoint is available, use it
        if elapsed >= alt_endpoint["delay"]:
            current_api_index = alt_index
            return current_api_index
    
    # If no immediately available endpoint is found, use the one that will be ready soonest
    best_wait_time = float('inf')
    best_index = current_api_index
    
    for i, endpoint in enumerate(API_ENDPOINTS):
        if not endpoint["enabled"]:
            continue
            
        elapsed = current_time - endpoint["last_request"]
        if elapsed < endpoint["delay"]:
            wait_time = endpoint["delay"] - elapsed
            if wait_time < best_wait_time:
                best_wait_time = wait_time
                best_index = i
    
    current_api_index = best_index
    return current_api_index

async def check_username_availability(username: str) -> Tuple[bool, int, str]:
    """
    Check if a Roblox username is available using multiple API endpoints.
    
    Args:
        username (str): The username to check
        
    Returns:
        Tuple[bool, int, str]: A tuple containing:
            - Boolean indicating if the username is available
            - Status code from the API (or -1 for errors)
            - Message or reason for availability status
    
    Raises:
        Exception: If there's an error with the API requests that can't be handled
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
    
    # Select which API endpoint to use
    api_index = select_next_api()
    endpoint = API_ENDPOINTS[api_index]
    
    # Update the API's last request time
    endpoint["last_request"] = current_time
    
    # Set up the parameters for this API
    request_params = endpoint["params"].copy()
    if "request.username" in endpoint["params"]:
        request_params["request.username"] = username
    else:
        request_params["username"] = username
    
    # No retries - we'll switch APIs if there's an issue
    try:
        session = await get_session()
        async with session.get(endpoint["url"], params=request_params) as response:
            # Record the response status
            if response.status == 429:
                # Rate limited - increase the count and update delays
                endpoint["rate_limit_count"] += 1
                endpoint["success_streak"] = 0
                update_api_delays()
                
                # Try the other API instead
                logger.warning(f"{endpoint['name']} rate limited. Switching to alternate API.")
                alt_index = (api_index + 1) % len(API_ENDPOINTS)
                return await check_with_specific_api(username, alt_index)
            
            # Attempt to parse the JSON response
            try:
                data = await response.json()
            except Exception:
                # If we can't parse JSON, treat as an error
                endpoint["success_streak"] = 0
                message = f"Invalid JSON response from {endpoint['name']}"
                record_username_check(username, False, response.status, message)
                memory_cache[username] = (False, response.status, message, current_time)
                return False, response.status, message
            
            # Check the status code
            if response.status == 200:
                # Increment success streak
                endpoint["success_streak"] += 1
                
                # Process response
                is_available = False
                status_code = response.status
                message = ""
                
                # For both APIs, code 0 means available
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
                
                # If we've had several successes in a row, maybe adjust delays
                if endpoint["success_streak"] >= 10:
                    update_api_delays()
                
                return is_available, status_code, message
            else:
                # Other error
                endpoint["success_streak"] = 0
                message = f"API Error: HTTP {response.status} from {endpoint['name']}"
                
                # Store failed result
                record_username_check(username, False, response.status, message)
                memory_cache[username] = (False, response.status, message, current_time)
                
                return False, response.status, message
                
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        # Network error - increment error count and possibly disable endpoint
        endpoint["success_streak"] = 0
        endpoint["rate_limit_count"] += 1
        err_type = "Timeout" if isinstance(e, asyncio.TimeoutError) else "Network"
        logger.error(f"{err_type} error with {endpoint['name']}: {str(e)}")
        
        # If we've had multiple failures in a row, potentially disable this endpoint
        if endpoint["rate_limit_count"] >= 5:
            logger.warning(f"Disabling problematic endpoint: {endpoint['name']} due to repeated failures")
            endpoint["enabled"] = False
            
            # Make sure we have at least one endpoint enabled
            any_enabled = False
            for ep in API_ENDPOINTS:
                if ep["enabled"]:
                    any_enabled = True
                    break
                    
            if not any_enabled:
                logger.warning("All endpoints were disabled! Re-enabling primary endpoint.")
                API_ENDPOINTS[0]["enabled"] = True
                API_ENDPOINTS[0]["rate_limit_count"] = 0
        
        # Try an alternate API
        alt_index = None
        for i in range(1, len(API_ENDPOINTS)):
            check_index = (api_index + i) % len(API_ENDPOINTS)
            if API_ENDPOINTS[check_index]["enabled"]:
                alt_index = check_index
                break
                
        if alt_index is not None:
            return await check_with_specific_api(username, alt_index)
        else:
            # Fall back to the primary endpoint if no alternatives
            return await check_with_specific_api(username, 0)
            
    except Exception as e:
        # Unexpected error
        endpoint["success_streak"] = 0
        message = f"Unexpected error with {endpoint['name']}: {str(e)}"
        logger.error(message)
        record_username_check(username, False, 0, message)
        memory_cache[username] = (False, 0, message, current_time)
        return False, 0, message

async def check_with_specific_api(username: str, api_index: int) -> Tuple[bool, int, str]:
    """
    Check username with a specific API endpoint (used as fallback).
    
    Args:
        username (str): The username to check
        api_index (int): The index of the API endpoint to use
        
    Returns:
        Tuple[bool, int, str]: Same as check_username_availability
    """
    current_time = time.time()
    endpoint = API_ENDPOINTS[api_index]
    
    # If this endpoint was used too recently, wait
    elapsed = current_time - endpoint["last_request"]
    if elapsed < endpoint["delay"]:
        wait_time = endpoint["delay"] - elapsed
        logger.info(f"Waiting {wait_time:.2f}s before using {endpoint['name']}")
        await asyncio.sleep(wait_time)
    
    # Update the last request time
    endpoint["last_request"] = time.time()
    
    # Set up the parameters
    request_params = endpoint["params"].copy()
    if "request.username" in endpoint["params"]:
        request_params["request.username"] = username
    else:
        request_params["username"] = username
    
    try:
        session = await get_session()
        async with session.get(endpoint["url"], params=request_params) as response:
            # Record response status
            if response.status == 429:
                # Rate limited
                endpoint["rate_limit_count"] += 1
                endpoint["success_streak"] = 0
                update_api_delays()
                
                message = f"All APIs rate limited. Could not check username: {username}"
                logger.warning(message)
                record_username_check(username, False, 429, message)
                memory_cache[username] = (False, 429, message, current_time)
                return False, 429, message
            
            # Parse the JSON
            try:
                data = await response.json()
            except Exception:
                endpoint["success_streak"] = 0
                message = f"Invalid JSON response from {endpoint['name']}"
                record_username_check(username, False, response.status, message)
                memory_cache[username] = (False, response.status, message, current_time)
                return False, response.status, message
            
            # Process the response
            if response.status == 200:
                # Success
                endpoint["success_streak"] += 1
                
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
                
                # Store results
                record_username_check(username, is_available, status_code, message)
                memory_cache[username] = (is_available, status_code, message, current_time)
                
                return is_available, status_code, message
            else:
                # Error
                endpoint["success_streak"] = 0
                message = f"API Error: HTTP {response.status} from {endpoint['name']}"
                record_username_check(username, False, response.status, message)
                memory_cache[username] = (False, response.status, message, current_time)
                return False, response.status, message
    
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        # Network error with this API
        endpoint["success_streak"] = 0
        endpoint["rate_limit_count"] += 1
        err_type = "Timeout" if isinstance(e, asyncio.TimeoutError) else "Network"
        logger.error(f"{err_type} error with {endpoint['name']}: {str(e)}")
        
        # If we've had multiple failures in a row, potentially disable this endpoint
        if endpoint["rate_limit_count"] >= 5:
            logger.warning(f"Disabling problematic endpoint: {endpoint['name']} due to repeated failures")
            endpoint["enabled"] = False
            
            # Make sure we have at least one endpoint enabled
            any_enabled = False
            for ep in API_ENDPOINTS:
                if ep["enabled"]:
                    any_enabled = True
                    break
                    
            if not any_enabled:
                logger.warning("All endpoints were disabled! Re-enabling primary endpoint with reset error count.")
                API_ENDPOINTS[0]["enabled"] = True
                API_ENDPOINTS[0]["rate_limit_count"] = 0
        
        message = f"Connection error with {endpoint['name']}: {str(e)}"
        record_username_check(username, False, 0, message)
        memory_cache[username] = (False, 0, message, current_time)
        return False, 0, message
        
    except Exception as e:
        # Other unexpected error
        endpoint["success_streak"] = 0
        message = f"Error with {endpoint['name']}: {str(e)}"
        logger.error(message)
        record_username_check(username, False, 0, message)
        memory_cache[username] = (False, 0, message, current_time)
        return False, 0, message

# Clean up old memory cache entries periodically
async def clean_memory_cache():
    """Remove expired entries from the in-memory cache."""
    current_time = time.time()
    expired_keys = [k for k, (_, _, _, t) in memory_cache.items() 
                   if current_time - t >= MEMORY_CACHE_EXPIRY]
    for k in expired_keys:
        del memory_cache[k]
