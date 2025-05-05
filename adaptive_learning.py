"""
Adaptive learning module for the Roblox Username Bot.
This module implements self-improving algorithms to optimize bot performance.

It includes:
1. Dynamic parameter adjustment based on success rates
2. Smart cookie rotation with automatic error detection
3. Pattern learning for username generation
4. Performance metrics tracking
"""

import os
import json
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any

# Set up logging
logger = logging.getLogger('roblox_username_bot')

# Constants
MIN_SUCCESS_THRESHOLD = 0.05  # 5% minimum success rate before adaptation
MAX_PARALLEL_CHECKS = 30      # Maximum allowed parallel checks
MIN_PARALLEL_CHECKS = 5       # Minimum allowed parallel checks
SUCCESS_WINDOW_SIZE = 100     # Number of checks to consider for success rate calculation
ERROR_THRESHOLD = 5           # Number of consecutive errors before cookie switching
LEARNING_RATE = 0.1           # How quickly the system adapts (0.0-1.0)
COOKIE_COOLDOWN = 300         # Time in seconds before a failed cookie is tried again
LENGTH_DISTRIBUTION = {       # Default distribution of username lengths to try (weighted)
    3: 30.0,                  # Highest weight for 3-character usernames (using floats for type compatibility)
    4: 25.0,
    5: 20.0,
    6: 15.0,
    7: 5.0,
    8: 3.0,
    9: 2.0
}

class AdaptiveLearning:
    def __init__(self):
        # Performance metrics
        self.recent_checks = []  # List of (timestamp, is_available, error) tuples
        self.recent_lengths = {} # Dict of username_length: success_rate
        self.cookie_performance = {}  # Dict of cookie_index: success_stats
        self.pattern_success = {}  # Dict tracking successful patterns
        
        # Current parameters
        self.parallel_checks = 10
        self.length_weights = LENGTH_DISTRIBUTION.copy()
        self.pattern_weights = {}  # Will be populated as patterns emerge
        self.underscore_probability = 0.2
        self.numeric_probability = 0.3
        self.uppercase_probability = 0.4
        
        # Cookie management
        self.cookies = []
        self.cookie_status = []  # List of (last_used, success_count, error_count, cooldown_until)
        self.current_cookie_index = 0
        
        # Load initial cookies
        self._load_cookies()
        
        # Load saved state if exists
        self._load_state()
        
    def _load_cookies(self):
        """Load all available Roblox cookies from environment variables."""
        # Load the main cookie
        main_cookie = os.environ.get('ROBLOX_COOKIE')
        if main_cookie:
            self.cookies.append(main_cookie)
            self.cookie_status.append({
                'last_used': time.time(),
                'success_count': 0,
                'error_count': 0,
                'cooldown_until': 0
            })
            
        # Load numbered cookies (ROBLOX_COOKIE1, ROBLOX_COOKIE2, etc.)
        for i in range(1, 10):  # Check for up to 10 additional cookies
            cookie = os.environ.get(f'ROBLOX_COOKIE{i}')
            if cookie:
                self.cookies.append(cookie)
                self.cookie_status.append({
                    'last_used': time.time(),
                    'success_count': 0,
                    'error_count': 0,
                    'cooldown_until': 0
                })
        
        logger.info(f"Loaded {len(self.cookies)} cookies for adaptive rotation")
        
    def _load_state(self):
        """Load saved learning state if it exists."""
        try:
            if os.path.exists('adaptive_state.json'):
                with open('adaptive_state.json', 'r') as f:
                    state = json.load(f)
                    
                # Load saved parameters
                if 'length_weights' in state:
                    self.length_weights = state['length_weights']
                if 'parallel_checks' in state:
                    self.parallel_checks = state['parallel_checks']
                if 'pattern_weights' in state:
                    self.pattern_weights = state['pattern_weights']
                if 'underscore_probability' in state:
                    self.underscore_probability = state['underscore_probability']
                if 'numeric_probability' in state:
                    self.numeric_probability = state['numeric_probability']
                if 'uppercase_probability' in state:
                    self.uppercase_probability = state['uppercase_probability']
                    
                logger.info("Loaded adaptive learning state successfully")
        except Exception as e:
            logger.error(f"Error loading adaptive state: {str(e)}")
    
    def save_state(self):
        """Save the current learning state to a file."""
        try:
            state = {
                'length_weights': self.length_weights,
                'parallel_checks': self.parallel_checks,
                'pattern_weights': self.pattern_weights,
                'underscore_probability': self.underscore_probability,
                'numeric_probability': self.numeric_probability,
                'uppercase_probability': self.uppercase_probability,
                'last_updated': datetime.now().isoformat()
            }
            
            with open('adaptive_state.json', 'w') as f:
                json.dump(state, f, indent=2)
                
            logger.info("Saved adaptive learning state")
        except Exception as e:
            logger.error(f"Error saving adaptive state: {str(e)}")
    
    def record_check(self, username: str, is_available: bool, error: bool = False):
        """
        Record the result of a username check for adaptation.
        
        Args:
            username (str): The username that was checked
            is_available (bool): Whether the username was available
            error (bool): Whether an error occurred during the check
        """
        current_time = time.time()
        
        # Add to recent checks
        self.recent_checks.append((current_time, is_available, error))
        
        # If we have too many checks, remove the oldest
        if len(self.recent_checks) > SUCCESS_WINDOW_SIZE:
            self.recent_checks.pop(0)
        
        # Update cookie performance for current cookie
        if self.current_cookie_index < len(self.cookie_status):
            if error:
                self.cookie_status[self.current_cookie_index]['error_count'] += 1
            else:
                if is_available:
                    self.cookie_status[self.current_cookie_index]['success_count'] += 1
                self.cookie_status[self.current_cookie_index]['last_used'] = current_time
        
        # Record success by length
        length = len(username)
        if length not in self.recent_lengths:
            self.recent_lengths[length] = []
        
        # Add this check to the appropriate length bucket
        self.recent_lengths[length].append((current_time, is_available, error))
        
        # Keep only the recent history for each length
        if len(self.recent_lengths[length]) > 50:  # Keep the 50 most recent for each length
            self.recent_lengths[length].pop(0)
            
        # Track pattern success if the username was available
        if is_available:
            # Extract patterns from successful username
            patterns = self._extract_patterns(username)
            
            # Update pattern success weights
            for pattern in patterns:
                if pattern not in self.pattern_weights:
                    self.pattern_weights[pattern] = 1
                else:
                    self.pattern_weights[pattern] += 1
    
    def _extract_patterns(self, username: str) -> List[str]:
        """Extract pattern features from a username."""
        patterns = []
        
        # Extract character type patterns (uppercase, lowercase, numeric)
        type_pattern = ""
        for char in username:
            if char.isupper():
                type_pattern += "U"
            elif char.islower():
                type_pattern += "L"
            elif char.isdigit():
                type_pattern += "N"
            else:
                type_pattern += "_"
        patterns.append(f"type:{type_pattern}")
        
        # Extract position patterns for special characters
        if '_' in username:
            patterns.append(f"underscore_pos:{username.index('_')}")
            
        # Record presence of special patterns
        has_underscore = '_' in username
        has_number = any(c.isdigit() for c in username)
        patterns.append(f"has_underscore:{has_underscore}")
        patterns.append(f"has_number:{has_number}")
        
        # Record length pattern
        patterns.append(f"length:{len(username)}")
        
        return patterns
    
    def adapt(self) -> Dict:
        """
        Analyze performance and adapt parameters for better results.
        
        Returns:
            Dict: The updated parameters
        """
        # Calculate current success rate
        if not self.recent_checks:
            return self._get_current_params()
            
        valid_checks = [(t, a, e) for t, a, e in self.recent_checks if not e]
        if not valid_checks:
            return self._get_current_params()
            
        total_valid = len(valid_checks)
        successful = sum(1 for _, available, _ in valid_checks if available)
        success_rate = successful / total_valid if total_valid > 0 else 0
        
        # Only adapt if we have enough data
        if total_valid < 20:
            return self._get_current_params()
            
        logger.info(f"Current success rate: {success_rate:.2%} ({successful}/{total_valid})")
        
        # Adapt parameters based on success rate
        self._adapt_parallel_checks(success_rate)
        self._adapt_length_weights()
        self._adapt_character_probabilities()
        
        # Save the state after adaptation
        self.save_state()
        
        return self._get_current_params()
    
    def _adapt_parallel_checks(self, success_rate: float):
        """Adapt the number of parallel checks based on success rate."""
        # If success rate is very low, reduce parallelism to avoid wasting API calls
        if success_rate < 0.01:  # Less than 1% success
            new_parallel = max(self.parallel_checks - 2, MIN_PARALLEL_CHECKS)
        # If success rate is decent and we're not getting errors, increase parallelism
        elif success_rate >= 0.05 and self._error_rate() < 0.1:
            new_parallel = min(self.parallel_checks + 1, MAX_PARALLEL_CHECKS)
        else:
            return  # No change needed
            
        # Apply change with learning rate
        change = (new_parallel - self.parallel_checks) * LEARNING_RATE
        self.parallel_checks = max(MIN_PARALLEL_CHECKS, 
                                  min(MAX_PARALLEL_CHECKS, 
                                      int(self.parallel_checks + change)))
        
        logger.info(f"Adapted parallel checks to {self.parallel_checks}")
    
    def _adapt_length_weights(self):
        """Adapt the weights for different username lengths based on success rates."""
        # Calculate success rate for each length
        length_success = {}
        
        for length, checks in self.recent_lengths.items():
            if len(checks) < 5:  # Skip lengths with too few checks
                continue
                
            valid_checks = [(t, a, e) for t, a, e in checks if not e]
            if not valid_checks:
                continue
                
            total_valid = len(valid_checks)
            successful = sum(1 for _, available, _ in valid_checks if available)
            success_rate = successful / total_valid if total_valid > 0 else 0
            
            length_success[length] = success_rate
        
        # No data to adapt with
        if not length_success:
            return
            
        # Get total success score to normalize
        total_score = sum(rate for rate in length_success.values())
        if total_score <= 0:
            return
            
        # Create new normalized weights
        new_weights = {}
        for length, rate in length_success.items():
            # We boost the weight of shorter usernames
            length_factor = 1.0
            if length <= 4:
                length_factor = 3.0  # Triple weight for short usernames
            elif length <= 6:
                length_factor = 1.5  # 50% more weight for medium usernames
                
            new_weights[length] = (rate / total_score) * 100 * length_factor
        
        # Blend with current weights using learning rate
        for length, weight in new_weights.items():
            if length in self.length_weights:
                self.length_weights[length] = (
                    (1 - LEARNING_RATE) * self.length_weights[length] + 
                    LEARNING_RATE * weight
                )
            else:
                self.length_weights[length] = weight
                
        # Add any missing lengths from default distribution
        for length, weight in LENGTH_DISTRIBUTION.items():
            if length not in self.length_weights:
                self.length_weights[length] = weight
                
        logger.info(f"Adapted length weights: {dict(sorted(self.length_weights.items()))}")
    
    def _adapt_character_probabilities(self):
        """Adapt character type probabilities based on successful patterns."""
        # Check if we have enough pattern data
        if not self.pattern_weights:
            return
            
        # Extract success statistics for different patterns
        underscore_success = 0
        non_underscore_success = 0
        numeric_success = 0
        non_numeric_success = 0
        uppercase_success = 0
        non_uppercase_success = 0
        
        for pattern, weight in self.pattern_weights.items():
            if pattern == "has_underscore:True":
                underscore_success += weight
            elif pattern == "has_underscore:False":
                non_underscore_success += weight
            elif pattern == "has_number:True":
                numeric_success += weight
            elif pattern == "has_number:False":
                non_numeric_success += weight
            elif pattern.startswith("type:") and "U" in pattern.split(":", 1)[1]:
                uppercase_success += weight
            elif pattern.startswith("type:") and "U" not in pattern.split(":", 1)[1]:
                non_uppercase_success += weight
        
        # Calculate new probabilities
        if underscore_success + non_underscore_success > 0:
            new_underscore_prob = underscore_success / (underscore_success + non_underscore_success)
            self.underscore_probability = (1 - LEARNING_RATE) * self.underscore_probability + LEARNING_RATE * new_underscore_prob
            
        if numeric_success + non_numeric_success > 0:
            new_numeric_prob = numeric_success / (numeric_success + non_numeric_success)
            self.numeric_probability = (1 - LEARNING_RATE) * self.numeric_probability + LEARNING_RATE * new_numeric_prob
            
        if uppercase_success + non_uppercase_success > 0:
            new_uppercase_prob = uppercase_success / (uppercase_success + non_uppercase_success)
            self.uppercase_probability = (1 - LEARNING_RATE) * self.uppercase_probability + LEARNING_RATE * new_uppercase_prob
            
        logger.info(f"Adapted probabilities: underscore={self.underscore_probability:.2f}, " 
                   f"numeric={self.numeric_probability:.2f}, uppercase={self.uppercase_probability:.2f}")
    
    def _error_rate(self) -> float:
        """Calculate the error rate from recent checks."""
        if not self.recent_checks:
            return 0.0
            
        total = len(self.recent_checks)
        errors = sum(1 for _, _, error in self.recent_checks if error)
        return errors / total if total > 0 else 0
    
    def get_current_params(self) -> Dict:
        """
        Get the current parameter settings.
        
        Returns:
            Dict: The current parameters
        """
        return self._get_current_params()
        
    def _get_current_params(self) -> Dict:
        """Get the current parameter settings."""
        return {
            "parallel_checks": self.parallel_checks,
            "length_weights": self.length_weights,
            "underscore_probability": self.underscore_probability,
            "numeric_probability": self.numeric_probability,
            "uppercase_probability": self.uppercase_probability
        }
    
    def get_next_cookie(self) -> Tuple[int, str]:
        """
        Get the next cookie to use, based on performance and error rates.
        
        Returns:
            Tuple[int, str]: The cookie index and cookie string
        """
        # If we don't have multiple cookies, just use the first one
        if len(self.cookies) <= 1:
            return 0, self.cookies[0] if self.cookies else ""
        
        # Check if current cookie is having issues
        current_status = self.cookie_status[self.current_cookie_index]
        current_time = time.time()
        
        # If the current cookie is in cooldown and there's an alternative, switch
        if (current_status['cooldown_until'] > current_time and
            any(s['cooldown_until'] <= current_time for s in self.cookie_status)):
            # Find the best alternative cookie
            return self._select_best_cookie()
        
        # If error count is over threshold, put cookie in cooldown and switch
        if current_status['error_count'] >= ERROR_THRESHOLD:
            logger.warning(f"Cookie {self.current_cookie_index} has too many errors, placing in cooldown")
            self.cookie_status[self.current_cookie_index]['cooldown_until'] = current_time + COOKIE_COOLDOWN
            self.cookie_status[self.current_cookie_index]['error_count'] = 0
            return self._select_best_cookie()
        
        # Otherwise, keep using the current cookie
        return self.current_cookie_index, self.cookies[self.current_cookie_index]
    
    def _select_best_cookie(self) -> Tuple[int, str]:
        """Select the best performing cookie that's not in cooldown."""
        current_time = time.time()
        
        # Find cookies not in cooldown
        available_cookies = [
            (i, self.cookie_status[i]) 
            for i in range(len(self.cookies)) 
            if self.cookie_status[i]['cooldown_until'] <= current_time
        ]
        
        if not available_cookies:
            # If all cookies are in cooldown, use the one with the shortest remaining cooldown
            shortest_cooldown = min(
                range(len(self.cookies)), 
                key=lambda i: self.cookie_status[i]['cooldown_until']
            )
            logger.warning(f"All cookies in cooldown, using cookie {shortest_cooldown} with shortest cooldown")
            return shortest_cooldown, self.cookies[shortest_cooldown]
        
        # Select the cookie with the highest success rate
        best_cookie = max(
            available_cookies,
            key=lambda ic: (
                ic[1]['success_count'] / max(1, ic[1]['success_count'] + ic[1]['error_count'])
            )
        )
        
        self.current_cookie_index = best_cookie[0]
        return self.current_cookie_index, self.cookies[self.current_cookie_index]
    
    def report_cookie_error(self, cookie_index: int):
        """Report an error with a specific cookie."""
        if 0 <= cookie_index < len(self.cookie_status):
            self.cookie_status[cookie_index]['error_count'] += 1
            logger.warning(f"Reported error for cookie {cookie_index}, " 
                          f"error count: {self.cookie_status[cookie_index]['error_count']}")
            
            # If this puts the cookie over the error threshold, put it in cooldown
            if self.cookie_status[cookie_index]['error_count'] >= ERROR_THRESHOLD:
                logger.warning(f"Cookie {cookie_index} has too many errors, placing in cooldown")
                self.cookie_status[cookie_index]['cooldown_until'] = time.time() + COOKIE_COOLDOWN
                self.cookie_status[cookie_index]['error_count'] = 0
    
    def get_length_distribution(self) -> Dict[int, float]:
        """
        Get the current probability distribution for username lengths.
        
        Returns:
            Dict[int, float]: A dictionary of length: probability
        """
        # Normalize weights to probabilities
        total_weight = sum(self.length_weights.values())
        if total_weight <= 0:
            # Convert values to float for type compatibility
            return {k: float(v) for k, v in LENGTH_DISTRIBUTION.items()}
            
        # Convert values to float for type compatibility
        return {k: float(v)/float(total_weight) for k, v in self.length_weights.items()}
    
    def get_character_probabilities(self) -> Dict[str, float]:
        """
        Get the current character type probabilities.
        
        Returns:
            Dict[str, float]: A dictionary of character_type: probability
        """
        return {
            "underscore": self.underscore_probability,
            "numeric": self.numeric_probability,
            "uppercase": self.uppercase_probability
        }
    
    def get_stats(self) -> Dict:
        """
        Get current performance statistics.
        
        Returns:
            Dict: Current performance metrics
        """
        # Calculate overall stats
        valid_checks = [(t, a, e) for t, a, e in self.recent_checks if not e]
        total_valid = len(valid_checks)
        successful = sum(1 for _, available, _ in valid_checks if available)
        success_rate = successful / total_valid if total_valid > 0 else 0
        
        # Calculate stats by length
        length_stats = {}
        for length, checks in self.recent_lengths.items():
            valid = [(t, a, e) for t, a, e in checks if not e]
            if not valid:
                continue
                
            total = len(valid)
            avail = sum(1 for _, available, _ in valid if available)
            rate = avail / total if total > 0 else 0
            length_stats[length] = {"checks": total, "available": avail, "rate": rate}
        
        # Cookie stats
        cookie_stats = []
        for i, status in enumerate(self.cookie_status):
            success = status['success_count']
            errors = status['error_count']
            rate = success / max(1, success + errors)
            cooldown = status['cooldown_until'] > time.time()
            
            cookie_stats.append({
                "index": i,
                "success_count": success,
                "error_count": errors,
                "success_rate": rate,
                "in_cooldown": cooldown,
                "is_current": i == self.current_cookie_index
            })
        
        return {
            "success_rate": success_rate,
            "total_checks": total_valid,
            "successful_checks": successful,
            "lengths": length_stats,
            "cookies": cookie_stats,
            "parameters": self._get_current_params(),
            "error_rate": self._error_rate()
        }