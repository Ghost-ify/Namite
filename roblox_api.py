"""
Roblox API integration for checking username availability.
This file contains functions to interact with the Roblox API.
"""
import asyncio
import aiohttp
import logging
from typing import Tuple

logger = logging.getLogger('roblox_username_bot')

# Roblox API endpoint for username validation
ROBLOX_USERNAME_API = "https://auth.roblox.com/v1/usernames/validate"

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
    params = {"request.username": username}
    
    # Maximum number of retries for transient errors
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(ROBLOX_USERNAME_API, params=params) as response:
                    # Parse the JSON response
                    data = await response.json()
                    
                    # Check the status code
                    if response.status == 200:
                        # According to the requirements, code 0 means available
                        if 'code' in data and data['code'] == 0:
                            return True, response.status, "Username is available"
                        else:
                            code = data.get('code', 'unknown')
                            message = data.get('message', 'Unknown reason')
                            return False, response.status, f"Code: {code}, Message: {message}"
                    elif response.status == 429:
                        # Rate limited, wait longer before retrying
                        logger.warning(f"Rate limited by Roblox API. Attempt {attempt+1}/{max_retries}")
                        await asyncio.sleep(retry_delay * (attempt + 2))  # Exponential backoff
                        continue
                    else:
                        return False, response.status, f"API Error: HTTP {response.status}"
                        
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
