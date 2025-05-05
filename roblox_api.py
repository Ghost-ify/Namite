"""
Roblox API integration for checking username availability.
This file contains functions to interact with the Roblox API.
"""
import asyncio
import logging
import time
import random
import math
import json
import urllib.parse
import os
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, List, Any
from database import record_username_check, is_username_in_cooldown, get_username_status

logger = logging.getLogger('roblox_username_bot')

# Browser simulation headers
BROWSER_HEADERS = [
    {
        # Chrome on Windows
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
        "Cache-Control": "no-cache"
    },
    {
        # Firefox on macOS
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Pragma": "no-cache"
    },
    {
        # Safari on iOS
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    },
    {
        # Edge on Windows
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.roblox.com/"
    }
]

# Roblox API endpoints for username validation (with fallback)
API_ENDPOINTS = [
    {
        "url": "https://auth.roblox.com/v1/usernames/validate",
        "params": {
            "request.username": "",
            "request.birthday": "1990-01-01"  # Add default birthday
        },
        "name": "Roblox Auth API",
        "delay": 0.5,  # Base delay between requests (will be adaptive)
        "rate_limit_count": 0,  # Count of 429 responses
        "last_request": 0,  # Timestamp of last request
        "success_streak": 0,  # Count of consecutive successful requests
        "enabled": True,  # Whether this API is currently enabled
        "headers_index": 0  # Index of headers to use, will rotate
    },
    {
        "url": "https://users.roblox.com/v1/usernames/validate",
        "params": {
            "username": "", 
            "type": "Username",
            "birthday": "1990-01-01"  # Add default birthday
        },
        "name": "Roblox Users API",
        "delay": 0.5,  # Base delay between requests (will be adaptive)
        "rate_limit_count": 0,  # Count of 429 responses
        "last_request": 0,  # Timestamp of last request
        "success_streak": 0,  # Count of consecutive successful requests
        "enabled": True,  # Whether this API is currently enabled
        "headers_index": 1  # Index of headers to use, will rotate
    },
    {
        "url": "https://accountsettings.roblox.com/v1/usernames/validate",
        "params": {
            "username": "",
            "birthday": "1990-01-01"  # Add default birthday
        },
        "name": "Roblox Account Settings API",
        "delay": 0.6,  # Start with slightly higher delay for this endpoint
        "rate_limit_count": 0,
        "last_request": 0,
        "success_streak": 0,
        "enabled": True,
        "headers_index": 2
    },
    {
        "url": "https://www.roblox.com/UserCheck/doesusernameexist",
        "params": {"username": ""},
        "name": "Roblox Legacy API",
        "delay": 0.7,  # Higher delay for legacy endpoint
        "rate_limit_count": 0,
        "last_request": 0,
        "success_streak": 0,
        "enabled": True,
        "headers_index": 3
    }
]

# Default API to use (will rotate between endpoints)
current_api_index = 0

# Don't use a global session - creates issues with binding
# Instead we'll create a new session for each request

# In-memory cache for very recent checks (to avoid hammering the database)
memory_cache: Dict[str, Tuple[bool, int, str, float]] = {}
MEMORY_CACHE_EXPIRY = 60  # 1 minute in seconds

# Exponential backoff parameters for retries
MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 10.0
JITTER_FACTOR = 0.25

# Random source ports to simulate multiple client IPs
# Use only a handful of ports that should be available
SOURCE_PORTS = [20123, 30123, 40123, 50123, 60123]

import http.client
import ssl

# Get all Roblox cookies from environment variables
ROBLOX_COOKIES = []

# Load all cookies with a more flexible approach
all_cookies = {}

# Base rate limits and dynamic parameters
COOKIES_PER_SECOND = 2.0     # Each cookie allows ~120 requests per minute
MIN_DELAY_BASE = 0.25        # Minimum delay between requests with one cookie
MIN_DELAY_MULTI = 0.15       # Minimum delay with multiple cookies
MAX_DELAY = 0.5             # Maximum delay between requests (on error)
INITIAL_DELAY = 0.25        # Initial delay before trying to go faster

# Scan environment variables for all Roblox cookies
for env_var, value in os.environ.items():
    if env_var.startswith('ROBLOX_COOKIE'):
        try:
            if env_var == 'ROBLOX_COOKIE':
                index = 0  # Main cookie gets index 0
            else:
                # Extract number after 'ROBLOX_COOKIE'
                index_str = env_var[13:]
                if index_str:
                    index = int(index_str)
                else:
                    logger.warning(f"Invalid cookie variable name format: {env_var}")
                    continue

            # Store cookie with its index for sorting later
            if value and len(value) > 50:  # Basic validation
                all_cookies[index] = value
            else:
                logger.warning(f"Skipping cookie {env_var} because it appears invalid (length: {len(value) if value else 0})")
        except ValueError:
            logger.warning(f"Skipping invalid cookie variable: {env_var}")
            continue

# Sort cookies by index and add to ROBLOX_COOKIES list
for index in sorted(all_cookies.keys()):
    cookie = all_cookies[index]
    ROBLOX_COOKIES.append(cookie)
    logger.info(f"Cookie #{index} loaded successfully (length: {len(cookie)})")

# Calculate dynamic delay based on number of cookies
cookie_count = len(ROBLOX_COOKIES)
if cookie_count > 0:
    # Calculate dynamic delay to achieve 90 requests/minute per cookie
    dynamic_min_delay = MIN_DELAY_BASE / cookie_count  # Distribute load across cookies
    dynamic_min_delay = max(MIN_DELAY_MULTI, dynamic_min_delay)  # Don't go too fast
    logger.info(f"Calculated dynamic minimum delay: {dynamic_min_delay:.3f}s based on {cookie_count} cookies")

    # Update API endpoint delays based on cookie count and performance
    for endpoint in API_ENDPOINTS:
        # Scale delay based on cookie count but maintain minimum safety threshold
        base_delay = endpoint["delay"] * (1 / (1 + math.log(cookie_count + 1)))
        success_bonus = 0.9 if endpoint["success_streak"] > 5 else 1.0
        endpoint["delay"] = max(dynamic_min_delay, base_delay * success_bonus)
        logger.info(f"Endpoint {endpoint['name']} delay set to {endpoint['delay']:.3f}s")

    logger.info(f"Successfully loaded {len(ROBLOX_COOKIES)} Roblox cookies for API requests")
else:
    logger.warning("No valid Roblox cookies found! Operating in unauthenticated mode, which may result in lower success rates.")

# Flag to track if we're using authenticated requests
USING_AUTH = len(ROBLOX_COOKIES) > 0

# Current cookie index to use (for rotation)
current_cookie_index = 0

# User agent for authenticated requests
AUTH_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Set authentication status directly if cookies are provided
AUTHENTICATED = USING_AUTH

if USING_AUTH:
    logger.info(f"Found {len(ROBLOX_COOKIES)} Roblox cookies, will use for API requests")
else:
    logger.info("Using anonymous Roblox API requests (no cookies provided)")

# Import adaptive learning system
from adaptive_learning import AdaptiveLearning

# Create an instance of the adaptive learning system
adaptive_system = AdaptiveLearning()

# Function to initialize adaptive learning system with all cookies
def initialize_with_cookies(cookies_list):
    global ROBLOX_COOKIES

    if not cookies_list:
        logger.warning("No cookies provided to initialize_with_cookies")
        return

    # Add cookies to ROBLOX_COOKIES if they don't exist already
    for cookie in cookies_list:
        if cookie not in ROBLOX_COOKIES:
            ROBLOX_COOKIES.append(cookie)

    # Log the number of cookies
    if len(ROBLOX_COOKIES) > 0:
        logger.info(f"roblox_api: Total of {len(ROBLOX_COOKIES)} cookies available")

    # Force reload cookies in adaptive learning system
    adaptive_system.cookies = ROBLOX_COOKIES.copy()

    # Initialize cookie status for each cookie
    adaptive_system.cookie_status = []
    for _ in range(len(adaptive_system.cookies)):
        adaptive_system.cookie_status.append({
            'last_used': time.time(),
            'success_count': 0,
            'error_count': 0,
            'cooldown_until': 0
        })

    logger.info(f"roblox_api: Initialized adaptive learning with {len(adaptive_system.cookies)} cookies")

# Get the next cookie in the rotation using smart load balancing
def get_cookies_for_request():
    """Get a list of available cookies for parallel requests."""
    if not ROBLOX_COOKIES:
        return [""]  # Return empty cookie if none available

    current_time = time.time()
    available_cookies = []

    if adaptive_system.cookies and adaptive_system.cookie_status:
        # Get all cookies not in cooldown
        for i, status in enumerate(adaptive_system.cookie_status):
            if status['cooldown_until'] <= current_time:
                # Calculate success rate
                total_requests = status['success_count'] + status['error_count']
                success_rate = status['success_count'] / max(1, total_requests)

                # Adjust cookie delay based on performance
                delay_multiplier = 1.0
                if success_rate < 0.4 and total_requests >= 10:
                    # Add increasing delay for poor performing cookies
                    delay_multiplier = 1 + ((0.4 - success_rate) * 10)  # Up to 4x slower
                    logger.info(f"Cookie {i} slowed down by {delay_multiplier}x due to poor performance")
                    time.sleep(2 * delay_multiplier)  # Extra delay before using this cookie

                available_cookies.append(ROBLOX_COOKIES[i])

    # Use all cookies but with appropriate delays
    if not available_cookies:
        available_cookies = ROBLOX_COOKIES.copy()

    return available_cookies

def get_next_cookie():
    """Legacy function kept for compatibility - returns first available cookie"""
    cookies = get_cookies_for_request()
    return cookies[0] if cookies else ""

async def make_http_request(url: str, params: dict, headers_index: int) -> Tuple[int, str]:
    """
    Make an HTTP request using the standard library to avoid issues with aiohttp.
    This is a more reliable approach that doesn't require binding to specific ports.

    Args:
        url (str): The URL to request
        params (dict): Query parameters
        headers_index (int): Index of headers to use from BROWSER_HEADERS

    Returns:
        Tuple[int, str]: Status code and response content
    """
    # Parse the URL
    parsed_url = urllib.parse.urlparse(url)
    host = parsed_url.netloc

    # Create the path with query string
    query_params = []
    for key, value in params.items():
        if value:  # Only add parameters with values
            query_params.append(f"{urllib.parse.quote(key)}={urllib.parse.quote(str(value))}")

    query_string = "&".join(query_params)
    path = f"{parsed_url.path}?{query_string}" if query_string else parsed_url.path

    # Get headers
    headers = BROWSER_HEADERS[headers_index % len(BROWSER_HEADERS)].copy()

    # Add some randomization to headers
    if random.random() < 0.3:
        headers["X-Requested-With"] = "XMLHttpRequest"

    # Add the Roblox cookie if available (for authenticated requests)
    if USING_AUTH and host.endswith("roblox.com"):
        # Get list of available cookies for this request
        available_cookies = get_cookies_for_request()
        # Use a random cookie from available ones
        current_cookie = random.choice(available_cookies)
        headers["Cookie"] = f".ROBLOSECURITY={current_cookie}"

        # Add common headers used by Roblox site
        headers["Origin"] = "https://www.roblox.com"
        headers["Referer"] = "https://www.roblox.com/"

        # Add CSRF token header if it's a POST request
        # For GET requests like availability checks, we don't need this

    # Add cache busting to avoid any caching issues
    headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    headers["Pragma"] = "no-cache"
    headers["Expires"] = "0"

    try:
        # Use HTTPS if the URL uses https
        if parsed_url.scheme == "https":
            # Create an SSL context
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection(host, timeout=10, context=context)
        else:
            conn = http.client.HTTPConnection(host, timeout=10)

        # Make the request - run in the executor to not block
        loop = asyncio.get_running_loop()

        # Execute the request in a separate thread to not block the event loop
        def perform_request():
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
            status = response.status
            content = response.read().decode('utf-8')
            conn.close()
            return status, content

        status, content = await loop.run_in_executor(None, perform_request)
        return status, content
    except Exception as e:
        logger.error(f"HTTP request error for {url}: {str(e)}")
        return -1, str(e)

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

async def get_user_details(username: str) -> Dict:
    """
    Get detailed information about a Roblox user if they exist.

    Args:
        username (str): The Roblox username to look up

    Returns:
        Dict: A dictionary containing user details if found, or None if not found:
            - user_id: The Roblox user ID
            - username: The Roblox username
            - display_name: The display name
            - created: The account creation date
            - avatar_url: URL to the user's avatar image
            - profile_url: URL to the user's profile
    """
    # Try to get user ID from username
    api_url = "https://users.roblox.com/v1/users/search"
    params = {
        "keyword": username,
        "limit": 10
    }

    try:
        status_code, response_text = await make_http_request(
            api_url, 
            params=params,
            headers_index=random.randint(0, len(BROWSER_HEADERS) - 1)
        )

        if status_code != 200:
            return None

        data = json.loads(response_text)

        # Find the exact username match
        matched_user = None
        for user in data.get("data", []):
            if user.get("name", "").lower() == username.lower():
                matched_user = user
                break

        if not matched_user:
            return None

        user_id = matched_user.get("id")

        # Get more user details
        user_url = f"https://users.roblox.com/v1/users/{user_id}"
        status_code, response_text = await make_http_request(
            user_url,
            params={},
            headers_index=random.randint(0, len(BROWSER_HEADERS) - 1)
        )

        if status_code != 200:
            return None

        user_data = json.loads(response_text)

        # Get avatar thumbnail
        avatar_url = f"https://thumbnails.roblox.com/v1/users/avatar?userIds={user_id}&size=420x420&format=Png"
        status_code, response_text = await make_http_request(
            avatar_url,
            params={},
            headers_index=random.randint(0, len(BROWSER_HEADERS) - 1)
        )

        avatar_image_url = None
        if status_code == 200:
            avatar_data = json.loads(response_text)
            if avatar_data.get("data") and len(avatar_data["data"]) > 0:
                avatar_image_url = avatar_data["data"][0].get("imageUrl")

        # Format creation date
        created_date = None
        if "created" in user_data:
            try:
                created_date = datetime.fromisoformat(user_data["created"].replace("Z", "+00:00"))
                # Calculate account age
                age_days = (datetime.now(timezone.utc) - created_date).days
                if age_days > 365:
                    years = age_days // 365
                    remaining_days = age_days % 365
                    account_age = f"{years} year{'s' if years != 1 else ''}, {remaining_days} day{'s' if remaining_days != 1 else ''}"
                else:
                    account_age = f"{age_days} day{'s' if age_days != 1 else ''}"
            except:
                account_age = "Unknown"
        else:
            account_age = "Unknown"

        return {
            "user_id": user_id,
            "username": user_data.get("name"),
            "display_name": user_data.get("displayName"),
            "created": user_data.get("created"),
            "account_age": account_age,
            "avatar_url": avatar_image_url,
            "profile_url": f"https://www.roblox.com/users/{user_id}/profile"
        }

    except Exception as e:
        return None

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
    # First check the database for 3-day cooldown
    from database import is_username_in_cooldown, get_username_status

    if is_username_in_cooldown(username):
        # Username was checked in the last 3 days, get the status from the database
        status = get_username_status(username)
        if status:
            logger.info(f"Username {username} is in 3-day cooldown period, using cached result")
            return status['is_available'], status['status_code'], status['message']

    # Check in-memory cache next (very recent checks)
    current_time = time.time()
    if username in memory_cache:
        is_available, status_code, message, timestamp = memory_cache[username]
        if current_time - timestamp < MEMORY_CACHE_EXPIRY:
            return is_available, status_code, message

    # We already checked for cooldown above, so this is redundant
    # Keeping the comment to make this clear

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

    # Make the HTTP request
    try:
        # Try to make the request with exponential backoff
        logger.info(f"Checking username '{username}' with endpoint: {endpoint['name']}")
        status_code, response_text = await make_http_request(
            endpoint["url"], 
            request_params,
            endpoint["headers_index"]
        )
        logger.info(f"API response for {username}: status={status_code}, response={response_text[:150]}")

        # Handle rate limiting
        if status_code == 429:
            # Rate limited - increase the count and update delays
            endpoint["rate_limit_count"] += 1
            endpoint["success_streak"] = 0
            update_api_delays()

            # Try another API endpoint
            logger.warning(f"{endpoint['name']} rate limited. Switching to alternate API.")
            alt_index = (api_index + 1) % len(API_ENDPOINTS)
            return await check_with_specific_api(username, alt_index)

        # Error with the request itself
        if status_code == -1:
            # Network error
            endpoint["success_streak"] = 0
            endpoint["rate_limit_count"] += 1
            message = f"Network error with {endpoint['name']}: {response_text}"
            logger.error(message)

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
                # Record the failure
                record_username_check(username, False, status_code, message)
                memory_cache[username] = (False, status_code, message, current_time)
                return False, status_code, message

        # Attempt to parse the JSON response
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # If we can't parse JSON, treat as an error
            endpoint["success_streak"] = 0
            message = f"Invalid JSON response from {endpoint['name']}"
            logger.error(f"{message}: {response_text[:100]}")
            record_username_check(username, False, status_code, message)
            memory_cache[username] = (False, status_code, message, current_time)
            # Report error to adaptive learning system
            adaptive_system.record_check(username, False, error=True)
            return False, status_code, message

        # Check the status code
        if status_code == 200:
            # Increment success streak
            endpoint["success_streak"] += 1

            # Process response
            is_available = False
            message = ""

            # For Roblox APIs, code 0 means available
            if 'code' in data and data['code'] == 0:
                is_available = True
                message = "Username is available"
                logger.info(f"AVAILABLE USERNAME FOUND: {username} - Response: {data}")
            else:
                code = data.get('code', 'unknown')
                msg = data.get('message', 'Unknown reason')
                message = f"Code: {code}, Message: {msg}"
                logger.debug(f"Username not available: {username} - Response: {json.dumps(data)[:150]}")

            # Store result in database
            record_username_check(username, is_available, status_code, message)

            # Store in memory cache
            memory_cache[username] = (is_available, status_code, message, current_time)

            # Record in adaptive learning system
            adaptive_system.record_check(username, is_available, error=False)

            # If we've had several successes in a row, maybe adjust delays
            if endpoint["success_streak"] >= 10:
                update_api_delays()
                # Run adaptive learning
                adaptive_system.adapt()

            return is_available, status_code, message
        else:
            # Other error
            endpoint["success_streak"] = 0
            message = f"API Error: HTTP {status_code} from {endpoint['name']}"

            # Store failed result
            record_username_check(username, False, status_code, message)
            memory_cache[username] = (False, status_code, message, current_time)

            return False, status_code, message

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
    # First check the database for 3-day cooldown
    from database import is_username_in_cooldown, get_username_status

    if is_username_in_cooldown(username):
        # Username was checked in the last 3 days, get the status from the database
        status = get_username_status(username)
        if status:
            logger.info(f"Username {username} is in 3-day cooldown period, using cached result (alt API)")
            return status['is_available'], status['status_code'], status['message']

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
        # Make the HTTP request
        logger.info(f"Checking username '{username}' with fallback endpoint: {endpoint['name']}")
        status_code, response_text = await make_http_request(
            endpoint["url"],
            request_params,
            endpoint["headers_index"]
        )
        logger.info(f"Fallback API response for {username}: status={status_code}, response={response_text[:150]}")

        # Record response status
        if status_code == 429:
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
            data = json.loads(response_text)
        except json.JSONDecodeError:
            endpoint["success_streak"] = 0
            message = f"Invalid JSON response from {endpoint['name']}"
            record_username_check(username, False, status_code, message)
            memory_cache[username] = (False, status_code, message, current_time)
            return False, status_code, message

        # Process the response
        if status_code == 200:
            # Success
            endpoint["success_streak"] += 1

            is_available = False
            message = ""

            if 'code' in data and data['code'] == 0:
                is_available = True
                message = "Username is available"
                logger.info(f"AVAILABLE USERNAME FOUND (alt API): {username} - Response: {data}")
            else:
                code = data.get('code', 'unknown')
                reason = data.get('message', 'Unknown reason')
                message = f"Code: {code}, Message: {reason}"
                logger.debug(f"Username not available (alt API): {username} - Response: {json.dumps(data)[:150]}")

            # Store results
            record_username_check(username, is_available, status_code, message)
            memory_cache[username] = (is_available, status_code, message, current_time)

            return is_available, status_code, message
        else:
            # Error
            endpoint["success_streak"] = 0
            message = f"API Error: HTTP {status_code} from {endpoint['name']}"
            record_username_check(username, False, status_code, message)
            memory_cache[username] = (False, status_code, message, current_time)
            return False, status_code, message

    except asyncio.TimeoutError as e:
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