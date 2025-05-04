"""
Roblox username generator module.
This file contains functions to generate random usernames following Roblox rules.

The generator creates short, memorable usernames (3-4 characters) to maximize the 
chance of finding available options.
"""
import random
import string
import logging
from typing import List, Set

logger = logging.getLogger('roblox_username_bot')

# Cached set of previously generated usernames to avoid duplicates
GENERATED_USERNAMES: Set[str] = set()

# List of common prefixes that can make usernames more appealing
COOL_PREFIXES = ['X', 'Z', 'Q', 'V', 'Ace', 'Pro', 'Evo', 'Neo', 'Max', 'Sky']

# Various patterns for generating names
PATTERNS = [
    # Pattern: Short 3-letter combo
    lambda: ''.join(random.choices(string.ascii_uppercase + string.digits, k=3)),
    
    # Pattern: Two letters + digit
    lambda: ''.join(random.choices(string.ascii_uppercase, k=2)) + random.choice(string.digits),
    
    # Pattern: Digit + two letters
    lambda: random.choice(string.digits) + ''.join(random.choices(string.ascii_uppercase, k=2)),
    
    # Pattern: Letter + underscore + letter
    lambda: random.choice(string.ascii_uppercase) + '_' + random.choice(string.ascii_uppercase),
    
    # Pattern: Very short: letter + digit
    lambda: random.choice(string.ascii_uppercase) + random.choice(string.digits),
    
    # Pattern: Very short: digit + letter
    lambda: random.choice(string.digits) + random.choice(string.ascii_uppercase),
    
    # Pattern: Three letters
    lambda: ''.join(random.choices(string.ascii_uppercase, k=3)),
    
    # Pattern: Ultra-short 1-letter 1-digit combo (these might be very valuable)
    lambda: random.choice(string.ascii_uppercase) + random.choice(string.digits),
]

def generate_username() -> str:
    """
    Generate a random Roblox-style username following these rules:
    - Length: 3-4 characters (predominantly, with some 2 character options)
    - Allowed characters: letters (a-z, A-Z), numbers (0-9), and underscore (_)
    - Cannot be fully numeric
    - Cannot start or end with an underscore
    - Maximum one underscore
    
    Returns:
        str: A randomly generated username
    """
    # Try to generate a unique username (not previously generated)
    for _ in range(5):  # Try up to 5 times to get a unique username
        # Choose a random pattern from our list
        pattern_func = random.choice(PATTERNS)
        username = pattern_func()
        
        # Make sure it's not all digits
        if username.replace('_', '').isdigit():
            # Replace a random digit with a letter
            position = random.randint(0, len(username) - 1)
            
            # Skip if this position has an underscore
            if username[position] == '_':
                # Find a non-underscore position
                non_underscore_positions = [i for i, char in enumerate(username) if char != '_']
                if non_underscore_positions:
                    position = random.choice(non_underscore_positions)
                else:
                    position = 0
            
            # Replace with a random letter
            username_chars = list(username)
            username_chars[position] = random.choice(string.ascii_uppercase)
            username = ''.join(username_chars)
        
        # If we've already generated this username before, try again
        if username in GENERATED_USERNAMES:
            continue
        
        # Add to our cache of generated usernames
        GENERATED_USERNAMES.add(username)
        
        logger.debug(f"Generated username: {username}")
        return username
    
    # Fallback in case we couldn't generate a unique username after 5 tries
    # (extremely unlikely but just to be safe)
    fallback = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    logger.debug(f"Generated fallback username: {fallback}")
    return fallback

# Clean up the cache of generated usernames if it gets too large
def clean_username_cache(max_size: int = 10000) -> None:
    """Remove excess usernames from the cache if it gets too large."""
    if len(GENERATED_USERNAMES) > max_size:
        # Convert to list, sort by random values, then take the first max_size elements
        # This randomly removes excess entries from the cache
        random_order = list(GENERATED_USERNAMES)
        random.shuffle(random_order)
        GENERATED_USERNAMES.clear()
        GENERATED_USERNAMES.update(random_order[:max_size])
