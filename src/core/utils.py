"""utility functions for data cleaning and formatting."""

import re
from calendar import monthrange
from datetime import datetime
from typing import Optional

from dateutil import parser as date_parser


def clean_currency(value: str | None) -> Optional[float]:
    """clean currency string and convert to float.
    
    handles european format (28.463,66) and standard format (28463.66).
    removes dots used as thousands separators, replaces commas with dots for decimals,
    strips currency symbols and whitespace.
    
    args:
        value: currency string (e.g., "28.463,66", "$100.50", "1,234.56")
        
    returns:
        float value or None if parsing fails
    """
    if not value:
        return None
    
    try:
        # convert to string and strip whitespace
        cleaned = str(value).strip()
        
        # remove common currency symbols
        cleaned = re.sub(r'[$€£¥₹]', '', cleaned)
        
        # remove any remaining whitespace
        cleaned = cleaned.replace(' ', '')
        
        # check if empty after cleaning
        if not cleaned:
            return None
        
        # detect format: if has comma, likely european format (28.463,66)
        # if has both dot and comma, determine which is decimal separator
        has_comma = ',' in cleaned
        has_dot = '.' in cleaned
        
        if has_comma and has_dot:
            # determine which is decimal separator based on position
            comma_pos = cleaned.rfind(',')
            dot_pos = cleaned.rfind('.')
            
            if comma_pos > dot_pos:
                # comma is decimal separator (e.g., "28.463,66")
                cleaned = cleaned.replace('.', '')  # remove thousands separator
                cleaned = cleaned.replace(',', '.')  # replace comma with dot
            else:
                # dot is decimal separator (e.g., "28,463.66")
                cleaned = cleaned.replace(',', '')  # remove thousands separator
        elif has_comma and not has_dot:
            # only comma: could be decimal or thousands separator
            # if comma is near the end (last 3 chars), it's likely decimal
            if len(cleaned) - cleaned.rfind(',') <= 3:
                cleaned = cleaned.replace(',', '.')
            else:
                # comma is thousands separator, remove it
                cleaned = cleaned.replace(',', '')
        elif has_dot and not has_comma:
            # only dot: could be decimal or thousands separator
            # if dot is near the end (last 3 chars), it's likely decimal
            # otherwise, it might be thousands separator - keep as is for now
            pass
        
        # convert to float
        result = float(cleaned)
        return result
        
    except (ValueError, AttributeError) as e:
        # return None if parsing fails
        return None


def validate_and_fix_date(date_str: str | None) -> Optional[str]:
    """validate and fix date string to yyyy-mm-dd format.
    
    handles partial dates like MM/YY or MM/YYYY by converting to full date
    using the last day of that month. if date is already valid, returns it.
    
    args:
        date_str: date string in various formats (yyyy-mm-dd, MM/YY, MM/YYYY, etc.)
        
    returns:
        date string in yyyy-mm-dd format or None if invalid
    """
    if not date_str:
        return None
    
    try:
        date_str = str(date_str).strip()
        
        # check for MM/YY or MM/YYYY format
        if '/' in date_str and len(date_str) <= 7:
            parts = date_str.split('/')
            if len(parts) == 2:
                month = int(parts[0])
                year_str = parts[1]
                
                # determine if it's YY or YYYY
                if len(year_str) == 2:
                    # assume 20XX for 2-digit years
                    year = 2000 + int(year_str)
                else:
                    year = int(year_str)
                
                # validate month
                if month < 1 or month > 12:
                    return None
                
                # get last day of the month
                last_day = monthrange(year, month)[1]
                
                # format as yyyy-mm-dd
                return f"{year}-{month:02d}-{last_day:02d}"
        
        # try to parse with dateutil (handles many formats)
        try:
            parsed_date = date_parser.parse(date_str, dayfirst=False, yearfirst=False)
            # return in yyyy-mm-dd format
            return parsed_date.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            # if dateutil fails, try standard formats
            pass
        
        # try yyyy-mm-dd format directly
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except ValueError:
            pass
        
        # if all parsing fails, return None
        return None
        
    except (ValueError, TypeError, AttributeError):
        return None

