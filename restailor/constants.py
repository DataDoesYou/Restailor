"""
Shared constants for the Resume Tailor application.

This module contains numeric constants that are used across multiple modules
to avoid magic numbers and improve code maintainability.
"""

# ============================================================================
# Time Conversion Constants
# ============================================================================

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * 60  # 3600
SECONDS_PER_DAY = 24 * 60 * 60  # 86400
SECONDS_PER_WEEK = 7 * 24 * 60 * 60  # 604800

MILLISECONDS_PER_SECOND = 1000
MILLISECONDS_PER_MINUTE = 60 * 1000
MILLISECONDS_PER_HOUR = 60 * 60 * 1000

# Convenience function for converting days to seconds
def days_to_seconds(days: int) -> int:
    """Convert days to seconds."""
    return days * SECONDS_PER_DAY
