"""
Roblox username generator module.
This file contains functions to generate random usernames following Roblox rules.

The generator creates usernames following these rules:
- Length: 3-20 characters
- Allowed characters: letters (a-z, A-Z), numbers (0-9), and underscore (_)
- Cannot be fully numeric
- Cannot start or end with an underscore
- Maximum one underscore
"""
import random
import string
import logging
from typing import List, Set
from database import is_username_in_cooldown

logger = logging.getLogger('roblox_username_bot')

# Various patterns for generating names
PATTERNS = [
    # Pattern: 3 characters
    lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=3)),
    
    # Pattern: 4 characters
    lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=4)),
    
    # Pattern: 5 characters
    lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=5)),
    
    # Pattern: 6 characters
    lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=6)),
    
    # Pattern: 7-10 characters
    lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(7, 10))),
    
    # Pattern: 11-15 characters
    lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(11, 15))),
    
    # Pattern: 16-20 characters
    lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(16, 20))),
    
    # Pattern: 3-5 characters with underscore in the middle
    lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(1, 2))) + 
           '_' + 
           ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(1, 3))),
    
    # Pattern: 6-10 characters with underscore
    lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(3, 5))) + 
           '_' + 
           ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(2, 5))),
    
    # Pattern: 4-character word-like (more vowels)
    lambda: generate_word_like(4),
    
    # Pattern: 5-character word-like (more vowels)
    lambda: generate_word_like(5),
    
    # Pattern: 6-character word-like (more vowels)
    lambda: generate_word_like(6),
    
    # Pattern: 7-10 character word-like (more vowels)
    lambda: generate_word_like(random.randint(7, 10)),
]

def generate_word_like(length: int) -> str:
    """Generate a more word-like username with more vowels."""
    vowels = 'aeiouAEIOU'
    consonants = ''.join(c for c in string.ascii_letters if c not in vowels)
    
    result = []
    
    # For longer names, add some structure by creating syllables
    if length > 8:
        # Create 2-3 syllable parts
        syllables = []
        remaining_length = length
        
        # Generate syllables until we're close to the target length
        while remaining_length > 3:
            syllable_length = min(random.randint(3, 5), remaining_length)
            syllable = []
            
            # Create syllable
            for i in range(syllable_length):
                if i % 2 == 0:
                    syllable.append(random.choice(consonants))
                else:
                    syllable.append(random.choice(vowels))
            
            syllables.append(''.join(syllable))
            remaining_length -= syllable_length
        
        # Fill in any remaining characters
        final_part = []
        for i in range(remaining_length):
            if i % 2 == 0:
                final_part.append(random.choice(consonants))
            else:
                final_part.append(random.choice(vowels))
        
        if final_part:
            syllables.append(''.join(final_part))
        
        result = ''.join(syllables)
    else:
        # For shorter names, use the original algorithm
        for i in range(length):
            # Alternate between consonants and vowels with some randomness
            if i % 2 == 0 or random.random() < 0.2:
                result.append(random.choice(consonants))
            else:
                result.append(random.choice(vowels))
        
        result = ''.join(result)
    
    # Capitalize some parts for readability in longer names
    if length > 6 and random.random() < 0.5:
        chars = list(result)
        # Capitalize 1-2 characters within the name for camelCase style
        caps_count = min(random.randint(1, 2), len(chars) - 1)
        for _ in range(caps_count):
            pos = random.randint(1, len(chars) - 1)
            chars[pos] = chars[pos].upper()
        result = ''.join(chars)
    
    return result

def generate_username_with_length(min_length: int = 3, max_length: int = 6) -> str:
    """
    Generate a random Roblox-style username within a specific length range.
    
    Args:
        min_length (int): Minimum username length (must be at least 3)
        max_length (int): Maximum username length (must be at most 20)
    
    Returns:
        str: A randomly generated username within the specified length range
    """
    # Ensure valid length boundaries
    min_length = max(3, min(min_length, 20))
    max_length = max(min_length, min(max_length, 20))
    
    # Try to generate a valid username that's not in cooldown
    for _ in range(15):  # Try up to 15 times for more chances within the range
        # Choose a pattern based on length range
        if min_length <= 4 and max_length <= 6:
            # For shorter usernames, prioritize short patterns
            pattern_options = [
                lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(min_length, max_length))),
                lambda: generate_word_like(random.randint(min_length, max_length)),
                lambda: ''.join(random.choices(string.ascii_letters, k=random.randint(min_length, max_length)))
            ]
            if max_length >= 5:  # Only add underscore pattern if length allows
                pattern_options.append(
                    lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(1, 2))) + 
                           '_' + 
                           ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(1, max_length-2)))
                )
        else:
            # For longer usernames
            pattern_options = [
                lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(min_length, max_length))),
                lambda: generate_word_like(random.randint(min_length, max_length)),
                lambda: ''.join(random.choices(string.ascii_letters, k=random.randint(min_length, max_length)))
            ]
            # Add underscore pattern if length allows
            if max_length >= 5:
                pattern_options.append(
                    lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(2, max_length//2))) + 
                           '_' + 
                           ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(min_length-3, max_length//2)))
                )
        
        pattern_func = random.choice(pattern_options)
        username = pattern_func()
        
        # Ensure length constraints
        if len(username) < min_length or len(username) > max_length:
            continue
            
        # Ensure no underscore at start or end
        if username.startswith('_') or username.endswith('_'):
            # Replace the underscore with a letter
            chars = list(username)
            if chars[0] == '_':
                chars[0] = random.choice(string.ascii_letters)
            if chars[-1] == '_':
                chars[-1] = random.choice(string.ascii_letters)
            username = ''.join(chars)
            
        # Ensure maximum one underscore
        if username.count('_') > 1:
            # Replace all but the first underscore
            first_underscore = username.find('_')
            chars = list(username)
            for i in range(len(chars)):
                if i != first_underscore and chars[i] == '_':
                    chars[i] = random.choice(string.ascii_letters)
            username = ''.join(chars)
            
        # Ensure not all numeric
        if username.replace('_', '').isdigit():
            # Replace a random digit with a letter
            non_underscore_positions = [i for i, char in enumerate(username) if char != '_']
            if non_underscore_positions:
                position = random.choice(non_underscore_positions)
                chars = list(username)
                chars[position] = random.choice(string.ascii_letters)
                username = ''.join(chars)
        
        # Check if username is in cooldown period (3 days)
        if not is_username_in_cooldown(username):
            logger.debug(f"Generated username with length {len(username)}: {username}")
            return username
    
    # Fallback in case we couldn't generate a valid username after 15 tries
    fallback_length = random.randint(min_length, max_length)
    fallback = ''.join(random.choices(string.ascii_letters, k=fallback_length-1)) + str(random.randint(0, 9))
    logger.debug(f"Generated fallback username: {fallback}")
    return fallback

def generate_username() -> str:
    """
    Generate a random Roblox-style username following these rules:
    - Adaptive length based on success rates (default 3-6 characters)
    - Allowed characters: letters (a-z, A-Z), numbers (0-9), and underscore (_)
    - Cannot be fully numeric
    - Cannot start or end with an underscore
    - Maximum one underscore
    
    Returns:
        str: A randomly generated username
    """
    try:
        # Import adaptive learning system
        from roblox_api import adaptive_system
        
        # Get the length distribution from the adaptive learning system
        length_distribution = adaptive_system.get_length_distribution()
        
        # Get character probabilities
        char_probs = adaptive_system.get_character_probabilities()
        
        # If we have a distribution, use it to pick a length
        if length_distribution:
            # Convert to list of (length, probability) tuples
            length_choices = list(length_distribution.items())
            # Select a length based on the probability distribution
            lengths, probabilities = zip(*length_choices)
            chosen_length = random.choices(lengths, weights=probabilities, k=1)[0]
            
            # Log the adaptive choice
            logger.debug(f"Adaptive learning chose length {chosen_length} from distribution {length_distribution}")
            
            # For very short usernames (3-4 chars), increase preference for underscore
            # This is because they tend to have higher success rates
            if chosen_length <= 4 and random.random() < char_probs.get('underscore', 0.2) * 1.5:
                if chosen_length == 3:
                    # For 3-char names with underscore, format is X_Y
                    first_char = random.choice(string.ascii_letters + string.digits)
                    last_char = random.choice(string.ascii_letters + string.digits)
                    if last_char.isdigit() and first_char.isdigit():
                        # Ensure not all numeric
                        last_char = random.choice(string.ascii_letters)
                    return f"{first_char}_{last_char}"
                else:
                    # For 4-char names, place underscore adaptively
                    underscore_pos = 1 if random.random() < 0.5 else 2
                    chars = []
                    for i in range(4):
                        if i == underscore_pos:
                            chars.append('_')
                        else:
                            # Use adaptive probability for digits vs letters
                            if random.random() < char_probs.get('numeric', 0.3):
                                chars.append(random.choice(string.digits))
                            else:
                                # Use adaptive probability for uppercase vs lowercase
                                if random.random() < char_probs.get('uppercase', 0.4):
                                    chars.append(random.choice(string.ascii_uppercase))
                                else:
                                    chars.append(random.choice(string.ascii_lowercase))
                    
                    result = ''.join(chars)
                    # Final validation check - ensure not all numeric except underscore
                    if result.replace('_', '').isdigit():
                        # Replace a random digit with a letter
                        non_underscore_positions = [i for i, char in enumerate(result) if char != '_']
                        if non_underscore_positions:
                            position = random.choice(non_underscore_positions)
                            chars = list(result)
                            chars[position] = random.choice(string.ascii_letters)
                            result = ''.join(chars)
                    return result
            
            # Generate a username with the selected length
            return generate_username_with_length(chosen_length, chosen_length)
        
        # Fallback to default 3-6 character range if no distribution
        return generate_username_with_length(3, 6)
    
    except Exception as e:
        # Log error but don't crash
        logger.error(f"Error in adaptive username generation: {str(e)}, falling back to default")
        # Fallback to default
        return generate_username_with_length(3, 6)

def validate_username(username: str) -> bool:
    """
    Validate that a username follows Roblox rules.
    
    Args:
        username (str): The username to validate
        
    Returns:
        bool: Whether the username is valid
    """
    # Check length (3-20 characters)
    if len(username) < 3 or len(username) > 20:
        return False
        
    # Check allowed characters
    if not all(c in string.ascii_letters + string.digits + '_' for c in username):
        return False
        
    # Check not starting or ending with underscore
    if username.startswith('_') or username.endswith('_'):
        return False
        
    # Check maximum one underscore
    if username.count('_') > 1:
        return False
        
    # Check not all numeric
    if username.replace('_', '').isdigit():
        return False
        
    return True
