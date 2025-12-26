#!/usr/bin/env python3
"""
Eventim Seat Availability Monitor

This script automatically monitors seat availability on Eventim pages by:
- Scraping the seating chart using Playwright
- Counting seats by color (yellow=available, red=available, grey=sold)
- Comparing with previous runs to detect new sales
- Running every 3 hours indefinitely

Requirements:
- pip install playwright
- playwright install

Author: AI Assistant
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Configuration
URL = "https://www.eventim.co.uk/event/cem-yilmaz-eventim-apollo-20391162/?affiliate=PP2"
DATA_FILE = Path("seat_data.json")
CHECK_INTERVAL = 3 * 60 * 60  # 3 hours in seconds
LOG_FILE = "seat_monitor.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def fetch_seat_data():
    """
    Fetch seat data from the Eventim page using Playwright.
    
    Returns:
        dict: Dictionary with seat counts by color
    """
    try:
        with sync_playwright() as p:
            # Launch browser in headless mode
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Set user agent to avoid detection
            page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            
            logger.info(f"Loading page: {URL}")
            page.goto(URL, wait_until="networkidle")
            
            # Wait for the seating chart to load - try multiple selectors
            selectors_to_try = [
                "svg",  # SVG seating chart
                "[class*='seat']",  # Seat elements
                "[class*='chart']",  # Chart container
                ".seatmap",  # Common seatmap class
                "[data-testid*='seat']"  # Test ID selectors
            ]
            
            chart_loaded = False
            for selector in selectors_to_try:
                try:
                    page.wait_for_selector(selector, timeout=10000)
                    chart_loaded = True
                    logger.info(f"Found seating chart with selector: {selector}")
                    break
                except PlaywrightTimeoutError:
                    continue
            
            if not chart_loaded:
                logger.warning("Could not find seating chart, trying to extract any available data...")
            
            # Initialize seat counts
            seat_counts = {"yellow": 0, "red": 0, "grey": 0}
            
            # Try multiple approaches to find seats
            seat_selectors = [
                "svg g[class*='seat']",  # SVG seats
                "svg circle[class*='seat']",  # Circular seats
                "svg rect[class*='seat']",  # Rectangular seats
                "[class*='seat']",  # Any seat elements
                "svg [fill]",  # Any SVG elements with fill color
                "svg [class*='available']",  # Available seats
                "svg [class*='sold']",  # Sold seats
            ]
            
            total_seats_found = 0
            
            for selector in seat_selectors:
                try:
                    seats = page.query_selector_all(selector)
                    if seats:
                        logger.info(f"Found {len(seats)} elements with selector: {selector}")
                        
                        for seat in seats:
                            # Get the fill color or class
                            fill_color = seat.get_attribute("fill")
                            class_name = seat.get_attribute("class") or ""
                            
                            # Determine seat status based on color or class
                            if fill_color:
                                fill_color = fill_color.lower()
                                if "yellow" in fill_color or "gold" in fill_color:
                                    seat_counts["yellow"] += 1
                                elif "red" in fill_color or "crimson" in fill_color:
                                    seat_counts["red"] += 1
                                elif "grey" in fill_color or "gray" in fill_color or "silver" in fill_color:
                                    seat_counts["grey"] += 1
                                else:
                                    # Try to infer from other colors
                                    if "green" in fill_color or "blue" in fill_color:
                                        seat_counts["yellow"] += 1  # Assume available
                                    else:
                                        seat_counts["grey"] += 1  # Assume sold
                            
                            # Also check class names for status
                            class_name = class_name.lower()
                            if "available" in class_name or "free" in class_name:
                                if "premium" in class_name or "vip" in class_name:
                                    seat_counts["red"] += 1
                                else:
                                    seat_counts["yellow"] += 1
                            elif "sold" in class_name or "taken" in class_name or "occupied" in class_name:
                                seat_counts["grey"] += 1
                            
                            total_seats_found += 1
                        
                        # If we found seats with this selector, break
                        if total_seats_found > 0:
                            break
                            
                except Exception as e:
                    logger.debug(f"Error with selector {selector}: {e}")
                    continue
            
            # If no seats found, try to get page content for debugging
            if total_seats_found == 0:
                logger.warning("No seats found, attempting to get page content for debugging...")
                page_content = page.content()
                if "seat" in page_content.lower() or "chart" in page_content.lower():
                    logger.info("Page contains seat-related content, but selectors may need adjustment")
                else:
                    logger.warning("Page may not contain seating chart or may be loading differently")
            
            browser.close()
            
            logger.info(f"Seat data extracted: {seat_counts}")
            return seat_counts
            
    except Exception as e:
        logger.error(f"Error fetching seat data: {e}")
        return {"yellow": 0, "red": 0, "grey": 0}


def load_previous_data():
    """
    Load previous seat data from the local JSON file.
    
    Returns:
        dict: Previous seat data or default values
    """
    try:
        if DATA_FILE.exists():
            with open(DATA_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
                logger.info(f"Loaded previous data: {data}")
                return data
        else:
            logger.info("No previous data file found, using defaults")
            return {"yellow": 0, "red": 0, "grey": 0}
    except Exception as e:
        logger.error(f"Error loading previous data: {e}")
        return {"yellow": 0, "red": 0, "grey": 0}


def save_current_data(data):
    """
    Save current seat data to the local JSON file.
    
    Args:
        data (dict): Current seat data to save
    """
    try:
        # Add timestamp to the data
        data_with_timestamp = {
            **data,
            "timestamp": datetime.now().isoformat(),
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open(DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(data_with_timestamp, file, indent=2)
        
        logger.info(f"Saved current data: {data}")
    except Exception as e:
        logger.error(f"Error saving current data: {e}")


def compare_and_notify(current, previous):
    """
    Compare current and previous data and print notifications if changes detected.
    
    Args:
        current (dict): Current seat data
        previous (dict): Previous seat data
    """
    changes_detected = False
    
    for color in ["yellow", "red", "grey"]:
        diff = current[color] - previous[color]
        if diff != 0:
            changes_detected = True
            category = "Yellow" if color == "yellow" else "Red" if color == "red" else "Sold (grey)"
            
            if diff > 0:
                print(f"🟢 More {category} seats available (+{diff})")
            else:
                print(f"🎟️ New tickets sold in category {category} ({diff})")
    
    if not changes_detected:
        print("📊 No changes detected since last check")


def print_seat_summary(data):
    """
    Print the seat availability summary.
    
    Args:
        data (dict): Seat data to display
    """
    print("\n" + "="*50)
    print("🎭 EVENTIM SEAT AVAILABILITY REPORT")
    print("="*50)
    print(f"🟡 Yellow (Available): {data['yellow']}")
    print(f"🔴 Red (Premium Available): {data['red']}")
    print(f"⚫ Sold (Grey): {data['grey']}")
    print(f"📅 Check Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)


def main():
    """
    Main function to run the seat monitoring script.
    """
    logger.info("Starting Eventim Seat Monitor")
    logger.info(f"Monitoring URL: {URL}")
    logger.info(f"Check interval: {CHECK_INTERVAL / 3600} hours")
    
    try:
        while True:
            print(f"\n🔍 Checking seat availability at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Fetch current seat data
            current_data = fetch_seat_data()
            
            # Load previous data
            previous_data = load_previous_data()
            
            # Print current seat counts
            print_seat_summary(current_data)
            
            # Compare with previous data and notify if needed
            compare_and_notify(current_data, previous_data)
            
            # Save current data for the next comparison
            save_current_data(current_data)
            
            # Wait for the next check
            hours = CHECK_INTERVAL / 3600
            print(f"\n⏰ Waiting for {hours} hours before next check...")
            print(f"Next check scheduled for: {(datetime.now().timestamp() + CHECK_INTERVAL):.0f}")
            print("-" * 50)
            
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
        print("\n👋 Seat monitoring stopped. Goodbye!")
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {e}")
        print(f"\n❌ Error occurred: {e}")
        print("The script will continue monitoring...")


if __name__ == "__main__":
    print("🎭 Eventim Seat Availability Monitor")
    print("=" * 40)
    print("This script will monitor seat availability every 3 hours.")
    print("Press Ctrl+C to stop monitoring.")
    print("=" * 40)
    
    main()

