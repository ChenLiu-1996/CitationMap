# Copyright (c) 2024 Chen Liu
# All rights reserved.
import random
import requests
import time
from bs4 import BeautifulSoup
from typing import List


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
                print("[WARNING!] Could not find author links for ", title_text)
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

    headers = requests.utils.default_headers()
    headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0',
    })

    time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.

    # Search the url of all citing papers.
    response = requests.get(paper_url, headers=headers)
    if response.status_code != 200:
        raise Exception('Failed to fetch the Google Scholar page')

    # Get the HTML data.
    soup = BeautifulSoup(response.text, 'html.parser')

    # Check for common indicators of blocking
    if 'CAPTCHA' in soup.text or 'not a robot' in soup.text:
        print('[WARNING!] Blocked by CAPTCHA or robot check when searching %s.' % paper_url)
        return []

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

            response = requests.get(next_url, headers=headers)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, 'html.parser')
            citing_authors_and_citing_papers += get_html_per_citation_page(soup)
        else:
            continue

    return citing_authors_and_citing_papers

def get_organization_name(organization_id: str) -> str:
    '''
    Get the official name of the organization defined by the unique Google Scholar organization ID.
    '''

    headers = requests.utils.default_headers()
    headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0',
    })

    url = f'https://scholar.google.com/citations?view_op=view_org&org={organization_id}&hl=en'

    time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f'When getting organization name, failed to fetch {url}: {response.text}.')

    soup = BeautifulSoup(response.text, 'html.parser')
    tag = soup.find('h2', {'class': 'gsc_authors_header'})
    if not tag:
        raise Exception(f'When getting organization name, failed to parse {url}.')
    return tag.text.replace('Learn more', '').strip()
