# Copyright (c) 2024 Chen Liu
# All rights reserved.
import random
import time
from bs4 import BeautifulSoup
from typing import List
from selenium import webdriver

NO_AUTHOR_FOUND_STR = 'No_author_found'

# Observation: the Nominatim package is very bad at getting the geolocation of companies (geolocation of universities are fine).
# Temporary solution: hard code the geolocations of the companies.
# NOTE: The headquarter represents the whole company which usually has many offices accross the world.
KNOWN_AFFILIATION_DICT = {
    'amazon': ('King County', 'Seattle', 'Washington', 'USA', 47.622721, -122.337176),
    'meta': ('Menlo Park', 'San Mateo', 'California', 'USA', 37.4851, -122.1483),
    'microsoft': ('King County', 'Redmond', 'Washington', 'USA', 47.645695, -122.131803),
    'ibm': ('Westchester', 'Armonk', 'New York', 'USA', 41.108252, -73.719887),
    'google': ('Santa Clara', 'Mountain View', 'California', 'USA', 37.421473, -122.080679),
    'morgan stanley': ('New York', 'New York', 'New York', 'USA', 40.760251, -73.98518),
    'siemens healthineers': ('Forchheim', 'Forchheim', 'Bavaria', 'Germany', 49.702088, 11.055870),
    'oracle': ('Travis', 'Austin', 'Texas', 'USA', 30.242913, -97.721641)
}

global_driver = None

def get_driver():
    global global_driver
    if global_driver is None:
        # Configure Chrome options to avoid bot detection
        options = webdriver.ChromeOptions()

        # Add user agent to mimic a real browser
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        # Disable automation flags
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Additional options to appear more like a normal browser
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-gpu')

        # Set window size to avoid headless detection
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--start-maximized')

        # Initialize the driver with options
        global_driver = webdriver.Chrome(options=options)

        # Execute CDP commands to further mask automation
        global_driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        global_driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("[INFO] Browser opened with anti-detection measures.")
        print("[INFO] You can solve CAPTCHAs (if prompted) in the browser window.")
        print("[INFO] KEEP THE POP-UP BROWSER OPEN until the CitationMap program is complete.")
    return global_driver

def wait_for_captcha(driver):
    '''
    Wait for user to solve CAPTCHA if present.
    '''
    page_source = driver.page_source
    if 'CAPTCHA' in page_source or 'not a robot' in page_source:
        print("\n" + "="*60)
        print("CAPTCHA DETECTED! Please solve it in the browser.")
        print("Press Enter here after you've solved it...")
        print("="*60)
        input()  # Wait for user to press Enter
        time.sleep(1)
    return

def get_html_per_citation_page(soup) -> List[str]:
    '''
    Utility to query each page containing results for
    cited work.
    Parameters
    --------
    soup: Beautiful Soup object pointing to current page.
    '''
    citing_authors_and_citing_papers = []

    for result in soup.find_all('div', class_='gs_ri'):
        title_tag = result.find('h3', class_='gs_rt')
        if title_tag:
            paper_parsed = False
            author_links = result.find_all('a', href=True)
            title_text = title_tag.get_text()
            title = title_text.replace('[HTML]', '').replace('[PDF]', '')
            for link in author_links:
                if 'user=' in link['href']:
                    author_id = link['href'].split('user=')[1].split('&')[0]
                    citing_authors_and_citing_papers.append((author_id, title))
                    paper_parsed = True
            if not paper_parsed:
                print("[WARNING!] Could not find author links for ", title)
                citing_authors_and_citing_papers.append((NO_AUTHOR_FOUND_STR, title))
        else:
            continue
    return citing_authors_and_citing_papers


def get_citing_author_ids_and_citing_papers(paper_url: str) -> List[str]:
    '''
    Find the (Google Scholar IDs of authors, titles of papers) who cite a given paper on Google Scholar.

    Parameters
    --------
    paper_url: URL of the paper BEING cited.
    '''
    citing_authors_and_citing_papers = []

    driver = get_driver()
    time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.

    # Search the url of all citing papers.
    driver.get(paper_url)
    wait_for_captcha(driver)

    # Get the HTML data.
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    # Check for common indicators of blocking
    if 'Access Denied' in soup.text or 'Forbidden' in soup.text:
        print('[WARNING!] Access denied or forbidden when searching searching %s.' % paper_url)
        return []

    # Loop through the citation results and find citing authors and papers.
    current_page_number = 1
    citing_authors_and_citing_papers += get_html_per_citation_page(soup)

    # Find the page navigation.
    navigation_buttons = soup.find_all('a', class_='gs_nma')
    for navigation in navigation_buttons:
        page_number_str = navigation.text
        if page_number_str and page_number_str.isnumeric() and int(page_number_str) == current_page_number + 1:
            # Found the correct button for next page.
            current_page_number += 1
            next_url = 'https://scholar.google.com' + navigation['href']
            time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.

            driver.get(next_url)
            wait_for_captcha(driver)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            citing_authors_and_citing_papers += get_html_per_citation_page(soup)
        else:
            continue

    return citing_authors_and_citing_papers

def get_organization_name(organization_id: str) -> str:
    '''
    Get the official name of the organization defined by the unique Google Scholar organization ID.
    '''

    driver = get_driver()
    time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.

    url = f'https://scholar.google.com/citations?view_op=view_org&org={organization_id}&hl=en'

    time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.

    driver.get(url)
    wait_for_captcha(driver)

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    tag = soup.find('h2', {'class': 'gsc_authors_header'})
    if not tag:
        raise Exception(f'When getting organization name, failed to parse {url}.')
    return tag.text.replace('Learn more', '').strip()
