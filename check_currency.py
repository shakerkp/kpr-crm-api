# check_currency.py
from db_manager import get_app_settings, update_app_settings
import datetime
import os

print(f"[{datetime.datetime.now()}] Currency Check Script Started.")

# Check if FreeSans.ttf exists and is being registered
freesans_path = 'FreeSans.ttf'
freesans_bold_path = 'FreeSansBold.ttf'

if os.path.exists(freesans_path) and os.path.exists(freesans_bold_path):
    print(f"[{datetime.datetime.now()}] Font Files Check: FreeSans.ttf and FreeSansBold.ttf found.")
else:
    print(f"[{datetime.datetime.now()}] Font Files Check: WARNING! One or both FreeSans font files are MISSING.")
    print(f"  FreeSans.ttf exists: {os.path.exists(freesans_path)}")
    print(f"  FreeSansBold.ttf exists: {os.path.exists(freesans_bold_path)}")
    print("  Please ensure 'FreeSans.ttf' and 'FreeSansBold.ttf' are in the same directory as this script.")

# Get current app settings
settings = get_app_settings()
current_currency_symbol = settings.get('currency_symbol', 'DEFAULT_NOT_SET')

print(f"[{datetime.datetime.now()}] Current currency symbol in DB settings: '{current_currency_symbol}'")

# Desired currency symbol
desired_currency_symbol = '₹' # Set this to the Rupee symbol

if current_currency_symbol != desired_currency_symbol:
    print(f"[{datetime.datetime.now()}] Currency symbol is not '{desired_currency_symbol}'. Updating...")
    try:
        update_app_settings(currency_symbol=desired_currency_symbol)
        print(f"[{datetime.datetime.now()}] Currency symbol successfully updated to '{desired_currency_symbol}'.")
    except Exception as e:
        print(f"[{datetime.datetime.now()}] ERROR: Failed to update currency symbol: {e}")
else:
    print(f"[{datetime.datetime.now()}] Currency symbol is already set to '{desired_currency_symbol}'. No update needed.")

print(f"[{datetime.datetime.now()}] Currency Check Script Finished.")

