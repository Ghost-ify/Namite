"""
Database utilities for the Roblox Username Bot.
"""
import os
import logging
import psycopg2
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, List

logger = logging.getLogger('roblox_username_bot')

# SQL for creating the database tables if they don't exist
INIT_DATABASE_SQL = """
-- Table for tracking username checks
CREATE TABLE IF NOT EXISTS checked_usernames (
    username VARCHAR(20) PRIMARY KEY,
    checked_at TIMESTAMP NOT NULL,
    is_available BOOLEAN NOT NULL,
    status_code INTEGER NOT NULL,
    message TEXT NOT NULL
);

-- Index for quick retrieval of recently available usernames
CREATE INDEX IF NOT EXISTS idx_available_checked_at 
ON checked_usernames (is_available, checked_at DESC);

-- Index for checking cooldown period
CREATE INDEX IF NOT EXISTS idx_username_checked_at 
ON checked_usernames (username, checked_at);
"""

def init_database():
    """Initialize the database with required tables."""
    conn = None
    try:
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        with conn.cursor() as cur:
            cur.execute(INIT_DATABASE_SQL)
            conn.commit()
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def get_db_connection():
    """Get a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        return None

def record_username_check(username: str, is_available: bool, status_code: int, message: str) -> bool:
    """
    Record a username check in the database.
    
    Args:
        username (str): The username that was checked
        is_available (bool): Whether the username is available
        status_code (int): The status code from the API
        message (str): The message from the API
        
    Returns:
        bool: Whether the operation was successful
    """
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            # Insert or update the username record
            cur.execute(
                """
                INSERT INTO checked_usernames (username, checked_at, is_available, status_code, message)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (username) 
                DO UPDATE SET 
                    checked_at = %s,
                    is_available = %s,
                    status_code = %s,
                    message = %s
                """,
                (
                    username, datetime.now(), is_available, status_code, message,
                    datetime.now(), is_available, status_code, message
                )
            )
            # Only commit every 10 operations or for available usernames
            if is_available or cur.rowcount % 10 == 0:
                conn.commit()
            return True
    except Exception as e:
        logger.error(f"Database error recording username check: {str(e)}")
        return False
    finally:
        conn.close()

def is_username_in_cooldown(username: str) -> bool:
    """
    Check if a username is in the cooldown period (3 days).
    
    Args:
        username (str): The username to check
        
    Returns:
        bool: True if the username was checked within the last 3 days
    """
    conn = get_db_connection()
    if not conn:
        return False  # If we can't connect to the database, assume not in cooldown
    
    try:
        with conn.cursor() as cur:
            # Check if the username was checked within the last 3 days
            cooldown_date = datetime.now() - timedelta(days=3)
            cur.execute(
                "SELECT 1 FROM checked_usernames WHERE username = %s AND checked_at > %s",
                (username, cooldown_date)
            )
            return cur.fetchone() is not None
    except Exception as e:
        logger.error(f"Database error checking username cooldown: {str(e)}")
        return False  # If there's an error, assume not in cooldown
    finally:
        conn.close()

def get_username_status(username: str) -> Optional[Dict]:
    """
    Get the status of a username from the database.
    
    Args:
        username (str): The username to check
        
    Returns:
        Optional[Dict]: Information about the username if it exists in the database
    """
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT username, checked_at, is_available, status_code, message
                FROM checked_usernames 
                WHERE username = %s
                """,
                (username,)
            )
            result = cur.fetchone()
            
            if result:
                return {
                    'username': result[0],
                    'checked_at': result[1],
                    'is_available': result[2],
                    'status_code': result[3],
                    'message': result[4],
                    'cooldown_ends_at': result[1] + timedelta(days=3)
                }
            return None
    except Exception as e:
        logger.error(f"Database error getting username status: {str(e)}")
        return None
    finally:
        conn.close()

def get_recently_available_usernames(limit: int = 10) -> List[Dict]:
    """
    Get a list of recently available usernames.
    
    Args:
        limit (int): Maximum number of usernames to return
        
    Returns:
        List[Dict]: List of available username records
    """
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT username, checked_at, is_available, status_code, message
                FROM checked_usernames 
                WHERE is_available = TRUE
                ORDER BY checked_at DESC
                LIMIT %s
                """,
                (limit,)
            )
            results = cur.fetchall()
            
            return [
                {
                    'username': row[0],
                    'checked_at': row[1],
                    'is_available': row[2],
                    'status_code': row[3],
                    'message': row[4]
                }
                for row in results
            ]
    except Exception as e:
        logger.error(f"Database error getting available usernames: {str(e)}")
        return []
    finally:
        conn.close()

def cleanup_old_records(days: int = 30) -> int:
    """
    Clean up username records older than the specified number of days.
    
    Args:
        days (int): Number of days to keep records for
        
    Returns:
        int: Number of records deleted
    """
    conn = get_db_connection()
    if not conn:
        return 0
    
    try:
        with conn.cursor() as cur:
            cutoff_date = datetime.now() - timedelta(days=days)
            cur.execute(
                "DELETE FROM checked_usernames WHERE checked_at < %s",
                (cutoff_date,)
            )
            deleted_count = cur.rowcount
            conn.commit()
            return deleted_count
    except Exception as e:
        logger.error(f"Database error cleaning up old records: {str(e)}")
        return 0
    finally:
        conn.close()