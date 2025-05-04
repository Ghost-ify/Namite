"""
Roblox username generator module.
This file contains functions to generate random usernames following Roblox rules.
"""
import random
import string
import logging

logger = logging.getLogger('roblox_username_bot')

def generate_username():
    """
    Generate a random Roblox-style username following these rules:
    - Length: 3-5 characters
    - Allowed characters: letters (a-z, A-Z), numbers (0-9), and underscore (_)
    - Cannot be fully numeric
    - Cannot start or end with an underscore
    - Maximum one underscore
    
    Returns:
        str: A randomly generated username
    """
    # Decide on username length (3-5 characters)
    length = random.randint(3, 5)
    
    # Decide if we'll include an underscore (about 30% chance)
    include_underscore = random.random() < 0.3
    
    # Generate the username
    if include_underscore:
        # If we include an underscore, it cannot be at start or end
        # So we need at least 3 characters
        if length < 3:
            length = 3
            
        # Choose position for underscore (not first or last)
        underscore_position = random.randint(1, length - 2)
        
        # Generate characters before underscore
        before_underscore = ''.join(random.choices(
            string.ascii_letters + string.digits, 
            k=underscore_position
        ))
        
        # Generate characters after underscore
        after_underscore = ''.join(random.choices(
            string.ascii_letters + string.digits, 
            k=length - underscore_position - 1
        ))
        
        username = before_underscore + '_' + after_underscore
    else:
        # Generate username without underscore
        username = ''.join(random.choices(
            string.ascii_letters + string.digits, 
            k=length
        ))
    
    # Check if username is fully numeric, and fix if needed
    if username.replace('_', '').isdigit():
        # Replace a random digit with a letter
        position = random.randint(0, length - 1)
        
        # Skip if this position has an underscore
        if username[position] == '_':
            # Find a non-underscore position
            non_underscore_positions = [i for i, char in enumerate(username) if char != '_']
            if non_underscore_positions:
                position = random.choice(non_underscore_positions)
            else:
                # This should never happen, but just in case
                logger.warning("Could not find non-underscore position in username")
                position = 0
        
        # Replace with a random letter
        username_chars = list(username)
        username_chars[position] = random.choice(string.ascii_letters)
        username = ''.join(username_chars)
    
    logger.debug(f"Generated username: {username}")
    return username
