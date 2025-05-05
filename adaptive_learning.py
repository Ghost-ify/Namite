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
MAX_PARALLEL_CHECKS = 50      # Maximum allowed parallel checks
MIN_PARALLEL_CHECKS = 5       # Minimum allowed parallel checks
SUCCESS_WINDOW_SIZE = 100     # Number of checks to consider for success rate calculation
ERROR_THRESHOLD = 5           # Number of consecutive errors before cookie switching
LEARNING_RATE = 0.1           # How quickly the system adapts (0.0-1.0)
COOKIE_COOLDOWN = 300         # Time in seconds before a failed cookie is tried again
BASE_CHECKS_PER_COOKIE = 5    # Base number of checks per cookie
CHECKS_SCALING_FACTOR = 1.2   # How aggressively to scale checks with more cookies
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
        self.check_interval = 0.1  # Default interval between checks in seconds
        # Ensure all length weights are stored as integers->floats
        self.length_weights = {int(k): float(v) for k, v in LENGTH_DISTRIBUTION.items()}
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
        # Load cookies from environment variables starting with ROBLOX_COOKIE
        all_cookies = {}
        cookie_count = 0
        
        try:
            # Get all environment variables
            for env_var, value in os.environ.items():
                # Check if this is a Roblox cookie environment variable
                if env_var.startswith('ROBLOX_COOKIE'):
                    # Extract the cookie index if it has one (e.g., ROBLOX_COOKIE1 → 1)
                    try:
                        if env_var == 'ROBLOX_COOKIE':
                            index = 0  # Main cookie gets index 0
                        else:
                            index = int(env_var[13:])  # Extract number after 'ROBLOX_COOKIE'
                        
                        # Store the cookie with its index
                        all_cookies[index] = value
                        cookie_count += 1
                    except ValueError:
                        # If the environment variable doesn't follow the expected format, skip it
                        logger.warning(f"Skipping invalid cookie variable: {env_var}")
                        continue
            
            # Reset cookies and status lists
            self.cookies = []
            self.cookie_status = []
            
            # Sort cookies by their index and add them to the self.cookies list
            for index in sorted(all_cookies.keys()):
                cookie = all_cookies[index]
                if cookie and len(cookie) > 50:  # Basic validation to ensure it's a proper cookie
                    self.cookies.append(cookie)
                    self.cookie_status.append({
                        'last_used': time.time(),
                        'success_count': 0,
                        'error_count': 0,
                        'cooldown_until': 0
                    })
                    logger.info(f"Adaptive learning: Loaded Roblox cookie #{index} (length: {len(cookie)})")
                else:
                    logger.warning(f"Adaptive learning: Skipping invalid cookie at index {index} (length: {len(cookie) if cookie else 0})")
            
            # Log summary of loaded cookies
            if len(self.cookies) > 0:
                logger.info(f"Adaptive learning: Successfully loaded {len(self.cookies)} cookies for rotation")
            else:
                logger.warning("Adaptive learning: No valid Roblox cookies found! Performance may be degraded.")
        except Exception as e:
            logger.error(f"Error loading cookies in adaptive learning: {str(e)}")
            # Ensure we have at least an empty list
            self.cookies = []
            self.cookie_status = []
        
    def _load_state(self):
        """Load saved learning state if it exists."""
        try:
            if os.path.exists('adaptive_state.json'):
                with open('adaptive_state.json', 'r') as f:
                    state = json.load(f)
                    
                # Load saved parameters with proper type conversion
                if 'length_weights' in state:
                    # Ensure length_weights keys are integers and values are floats
                    self.length_weights = {int(k): float(v) for k, v in state['length_weights'].items()}
                if 'parallel_checks' in state:
                    self.parallel_checks = int(state['parallel_checks'])
                if 'pattern_weights' in state:
                    # Ensure pattern weights keys are strings
                    self.pattern_weights = {str(k): float(v) for k, v in state['pattern_weights'].items()}
                if 'underscore_probability' in state:
                    self.underscore_probability = float(state['underscore_probability'])
                if 'numeric_probability' in state:
                    self.numeric_probability = float(state['numeric_probability'])
                if 'uppercase_probability' in state:
                    self.uppercase_probability = float(state['uppercase_probability'])
                    
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
        length = int(len(username))  # Ensure length is always an int
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
                pattern_key = str(pattern)  # Ensure pattern key is a string
                if pattern_key not in self.pattern_weights:
                    self.pattern_weights[pattern_key] = 1.0  # Start with float value
                else:
                    self.pattern_weights[pattern_key] = float(self.pattern_weights[pattern_key]) + 1.0
    
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
        
        # Record length pattern - ensure we use string representation
        patterns.append(f"length:{str(len(username))}")
        
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
    
    def calculate_dynamic_values(self):
        """
        Calculate dynamic values based on the number of available cookies.
        Aggressively scales based on cookie performance and count.
        """
        cookie_count = len(self.cookies)
        if cookie_count == 0:
            return MIN_PARALLEL_CHECKS

        # Calculate performance metrics for each cookie
        good_cookies = 0
        total_success_rate = 0
        
        for status in self.cookie_status:
            total_requests = status['success_count'] + status['error_count']
            if total_requests > 0:
                success_rate = status['success_count'] / total_requests
                if success_rate > 0.9:  # 90% success rate threshold
                    good_cookies += 1
                total_success_rate += success_rate

        avg_success_rate = total_success_rate / cookie_count if cookie_count > 0 else 0
        
        # Dynamic scaling based on performance
        base_per_cookie = 12 if avg_success_rate > 0.95 else (
            10 if avg_success_rate > 0.9 else (
            8 if avg_success_rate > 0.8 else 6))

        # Aggressive but safe scaling
        scaling_factor = (1 + (good_cookies / cookie_count)) * (1 + math.log(cookie_count + 1, 2))
        
        # Calculate target requests/second per cookie
        optimal_checks = int(base_per_cookie * cookie_count * scaling_factor)
        
        # Safety caps
        min_checks = max(MIN_PARALLEL_CHECKS, cookie_count * 3)  # At least 3 checks per cookie
        max_checks = min(MAX_PARALLEL_CHECKS, cookie_count * 15)  # Max 15 checks per cookie
        
        optimal_checks = max(min_checks, min(optimal_checks, max_checks))
        
        # Adjust interval dynamically
        self.check_interval = max(0.05, 0.2 / cookie_count)  # Minimum 50ms between batches
        
        logger.info(f"Optimized for {cookie_count} cookies: {optimal_checks} parallel checks, {self.check_interval:.3f}s interval")
        return optimal_checks
        
    def _calculate_cookie_performance(self) -> float:
        """Calculate performance factor based on cookie success rates."""
        if not self.cookie_status:
            return 1.0
            
        # Calculate average success rate across cookies
        success_rates = []
        for status in self.cookie_status:
            total = status['success_count'] + status['error_count']
            if total > 0:
                rate = status['success_count'] / total
                success_rates.append(rate)
        
        if not success_rates:
            return 1.0
            
        # Return a factor between 0.5 and 1.5 based on performance
        avg_rate = sum(success_rates) / len(success_rates)
        return max(0.5, min(1.5, avg_rate * 2))
        
        # Ensure we don't exceed the maximum allowed
        optimal_checks = min(MAX_PARALLEL_CHECKS, max(MIN_PARALLEL_CHECKS, optimal_checks))
        
        # Log the calculation
        logger.info(f"Calculated optimal parallel checks: {optimal_checks} based on {cookie_count} cookies")
        
        return optimal_checks
    
    def _adapt_parallel_checks(self, success_rate: float):
        """Adapt the number of parallel checks based on success rate and cookie count."""
        try:
            # Get the base number of checks from cookie count
            cookie_based_checks = self.calculate_dynamic_values()
            
            # If success rate is very low, reduce parallelism to avoid wasting API calls
            if success_rate < 0.01:  # Less than 1% success
                new_parallel = max(int(cookie_based_checks * 0.7), int(MIN_PARALLEL_CHECKS))
            # If success rate is decent and we're not getting errors, increase parallelism
            elif success_rate >= 0.05 and self._error_rate() < 0.1:
                new_parallel = min(int(cookie_based_checks * 1.2), int(MAX_PARALLEL_CHECKS))
            else:
                # Use cookie-based calculation as default
                new_parallel = cookie_based_checks
                
            # Apply change with learning rate - ensure all values are numeric
            change = float(new_parallel - int(self.parallel_checks)) * float(LEARNING_RATE)
            self.parallel_checks = max(int(MIN_PARALLEL_CHECKS), 
                                      min(int(MAX_PARALLEL_CHECKS), 
                                          int(self.parallel_checks + change)))
            
            logger.info(f"Adapted parallel checks to {self.parallel_checks}")
        except Exception as e:
            # If any errors occur during adaptation, fallback to a safe value
            logger.error(f"Error in parallel checks adaptation: {str(e)}")
            self.parallel_checks = 10
    
    def _adapt_length_weights(self):
        """Adapt the weights for different username lengths based on success rates."""
        try:
            # Calculate success rate for each length
            length_success = {}
            
            for length_key, checks in self.recent_lengths.items():
                # Convert length to int to ensure comparison works properly
                length = int(length_key) if isinstance(length_key, str) else int(length_key)
                
                if len(checks) < 5:  # Skip lengths with too few checks
                    continue
                    
                valid_checks = [(t, a, e) for t, a, e in checks if not e]
                if not valid_checks:
                    continue
                    
                total_valid = len(valid_checks)
                successful = sum(1 for _, available, _ in valid_checks if available)
                success_rate = successful / total_valid if total_valid > 0 else 0
                
                # Store with integer key and float value
                length_success[length] = float(success_rate)
            
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
                # Make sure length is an integer for comparison
                length_int = int(length)
                length_factor = 1.0
                if length_int <= 4:
                    length_factor = 3.0  # Triple weight for short usernames
                elif length_int <= 6:
                    length_factor = 1.5  # 50% more weight for medium usernames
                    
                new_weights[int(length)] = float((rate / total_score) * 100 * length_factor)
            
            # Blend with current weights using learning rate
            for length, weight in new_weights.items():
                length = int(length)  # Ensure key is an integer
                if length in self.length_weights:
                    self.length_weights[length] = float(
                        (1 - float(LEARNING_RATE)) * float(self.length_weights[length]) + 
                        float(LEARNING_RATE) * float(weight)
                    )
                else:
                    self.length_weights[length] = float(weight)
                    
            # Add any missing lengths from default distribution
            for length, weight in LENGTH_DISTRIBUTION.items():
                length_key = int(length)  # Ensure key is an integer
                weight_value = float(weight)  # Ensure value is a float
                if length_key not in self.length_weights:
                    self.length_weights[length_key] = weight_value
                    
            logger.info(f"Adapted length weights: {dict(sorted(self.length_weights.items()))}")
        except Exception as e:
            # If any errors occur during adaptation, log them
            logger.error(f"Error in length weights adaptation: {str(e)}")
    
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
            # Ensure we're dealing with string patterns and float weights
            pattern_str = str(pattern)
            weight_float = float(weight)
            
            if pattern_str == "has_underscore:True":
                underscore_success += weight_float
            elif pattern_str == "has_underscore:False":
                non_underscore_success += weight_float
            elif pattern_str == "has_number:True":
                numeric_success += weight_float
            elif pattern_str == "has_number:False":
                non_numeric_success += weight_float
            elif pattern_str.startswith("type:") and "U" in pattern_str.split(":", 1)[1]:
                uppercase_success += weight_float
            elif pattern_str.startswith("type:") and "U" not in pattern_str.split(":", 1)[1]:
                non_uppercase_success += weight_float
        
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