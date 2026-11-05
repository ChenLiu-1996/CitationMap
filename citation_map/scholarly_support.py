# Copyright (c) 2024 Chen Liu
# All rights reserved.
"""Google Scholar fetching helpers, independent of scholarly's fetch machinery.

The coordinator owns one visible Selenium window for discovery and manual CAPTCHA
verification. Affiliation workers use standard-library HTTP requests and return
parsed profiles or ask the coordinator for browser assistance; they never launch
browsers or read terminal input. No installed scholarly code is patched.
"""
import random
import hashlib
import json
import os
import tempfile
import time
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.cookiejar import Cookie, CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPCookieProcessor, build_opener
from bs4 import BeautifulSoup
from typing import Callable, List, Optional, Tuple
from tqdm import tqdm
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

NO_AUTHOR_FOUND_STR = 'No_author_found'

# Observation: the Nominatim package is very bad at getting the geolocation of companies (geolocation of universities are fine).
# Temporary solution: hard code the geolocations of the companies.
# Only bare company names use these headquarters coordinates. Names that include
# an office or location are sent to the geocoder instead.
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
_captcha_lock = threading.Lock()

def get_driver():
    """Return the single Chrome instance shared by all browser-based lookups."""
    global global_driver
    # Only the coordinating thread uses Selenium. All stages share this window.
    # Eager navigation returns when the DOM is ready; callers explicitly wait for
    # the expected content or a challenge before parsing the page.
    if global_driver is None:
        options = webdriver.ChromeOptions()
        options.page_load_strategy = 'eager'
        # The optional web pilot runs Chrome in a Selenium container so visitors
        # can operate that same session through its noVNC browser view. Ordinary
        # scripts keep launching local Chrome exactly as before.
        remote_url = os.environ.get('CITATION_MAP_SELENIUM_URL')
        if remote_url:
            global_driver = webdriver.Remote(command_executor=remote_url, options=options)
        else:
            global_driver = webdriver.Chrome(options=options)
        global_driver.set_page_load_timeout(30)
        tqdm.write('[INFO] Shared Chrome window opened. Keep it open for CAPTCHA challenges.')
    return global_driver


def wait_for_captcha(driver):
    '''
    Wait for user to solve CAPTCHA if present.
    '''
    with _captcha_lock:
        _wait_for_captcha_locked(driver)


def _captcha_present(driver, source=None):
    """Recognize a challenge, rather than CAPTCHA words in research results."""
    soup = BeautifulSoup(driver.page_source if source is None else source, 'html.parser')
    # A failed verification redirect can itself show Google's Bad Request page.
    # Its /sorry URL does not mean there is still a CAPTCHA to solve.
    if 'malformed or illegal request' in soup.get_text(' ', strip=True).lower():
        return False
    if soup.select_one(
            'form[action*="/sorry"], .g-recaptcha, .h-captcha, '
            'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], '
            'input[name="captcha"], input[name="captcha_response"]') is not None:
        return True
    # A plain automated-query block offers no CAPTCHA. Do not repeatedly tell
    # the user to solve one solely because Google's error URL contains /sorry.
    if 'may be sending automated queries' in soup.get_text(' ', strip=True).lower():
        return False
    if urlparse(driver.current_url).path.startswith('/sorry'):
        return True
    # Scholar pages can contain CAPTCHA scripts and papers about CAPTCHA. Neither
    # means a verification challenge is actually on screen.
    for node in soup.select('script, style, template, .gs_ri, #gsc_a_b'):
        node.decompose()
    text = soup.get_text(' ', strip=True).lower()
    return any(marker in text for marker in (
        'unusual traffic', 'not a robot', 'complete the captcha',
        'solve the captcha', 'verify you are human'))


def _wait_for_captcha_locked(driver):
    while _captcha_present(driver):
        # Hold tqdm's display lock and clear the bars throughout the pause.
        # Plain prints inside this context keep the Enter prompt as the last line;
        # tqdm.write() would redraw the bar immediately after each message.
        with tqdm.external_write_mode():
            print("\n" + "="*60)
            print("CAPTCHA DETECTED! Please solve it in the browser.")
            print('Browser: %s. URL: %s' % (threading.current_thread().name, driver.current_url))
            print("="*60)
            print("Press Enter here after you have solved it...", flush=True)
            input()  # The progress bar resumes only after Enter is received.
        time.sleep(1)
    return


def wait_for_profile_content(driver, element_id, requested_url=None):
    """Pause for manual recovery until content or a definite missing page appears."""
    def ready(browser):
        source = browser.page_source
        soup = BeautifulSoup(source, 'html.parser')
        text = soup.get_text(' ', strip=True).lower()
        if 'malformed or illegal request' in text:
            return ('bad_request', source)
        # Check challenges before content: a challenge page can still contain
        # fragments of the results markup. It must never count as usable results.
        if _captcha_present(browser, source):
            return ('captcha', source)
        if soup.find(id=element_id) is not None:
            return ('content', source)
        if 'may be sending automated queries' in text:
            return ('query_block', source)
        if any(marker in text for marker in ('forbidden', 'access denied')):
            return ('blocked', source)
        if any(marker in text for marker in ('profile not found', '404.')):
            return ('missing', source)
        return False

    while True:
        try:
            state, source = WebDriverWait(driver, 20).until(ready)
        except TimeoutException:
            state = 'unrecognized'
        if state == 'captcha':
            wait_for_captcha(driver)
            # Verification can redirect or take time to load the results. Start
            # a fresh check rather than letting another challenge reach the parser.
            continue
        if state in ('content', 'missing'):
            # Parse this checked snapshot, rather than reading a redirected or
            # partially replaced page from Chrome a second time.
            return source

        # An access block or unfamiliar page needs the user's attention, even if
        # it does not contain one of our known CAPTCHA markers. Waiting for input
        # has no timeout, and repeated Enter presses do not discard partial work.
        # Keep the recovery prompt unobstructed for the entire input wait too.
        with tqdm.external_write_mode():
            if state == 'query_block':
                print('\n' + '='*60)
                print('GOOGLE SCHOLAR ACCESS PAUSED')
                print('Sorry, Google has flagged requests from your computer or network as suspicious. '
                      'CitationMap may be sending too many requests.')
                print('You can press Ctrl+C and rerun later after Google allows access again. '
                      'Rerunning will resume from saved progress.')
                print('='*60, flush=True)
                # This is an access block, not a verification task. Wait silently
                # so no CAPTCHA prompt, page details, or progress bar follows it.
                input()
                continue
            elif state == 'bad_request':
                print('\n[WARNING] Google rejected this request as malformed or illegal. '
                      'This error page is not a CAPTCHA.')
            else:
                print('\n[WARNING] Google Scholar has not provided the expected content (%s).' % element_id)
            if requested_url:
                print('Requested Scholar URL: %s' % requested_url)
            print('URL: %s. Page title: %s.' % (driver.current_url, driver.title))
            print('Check the shared Chrome window. Wait for the page to load, or reload it '
                  'and resolve any access challenge. Keep Chrome open. '
                  'This run will wait for you; press Ctrl+C to stop.')
            # Keep this prompt compatible with the desktop app's Continue button.
            print('Press Enter here after you have solved it...', flush=True)
            input()


def _load_scholar_page(driver, url, element_id):
    """Recover from navigation timeouts using the existing visible Chrome page."""
    try:
        driver.get(url)
    except TimeoutException:
        # Chrome can time out before our content/CAPTCHA check gets a chance to
        # run. The page may still be loading; do not close or skip that page.
        tqdm.write('[WARNING] Chrome navigation timed out for %s. Checking the open page.' % url)
    return wait_for_profile_content(driver, element_id, requested_url=url)


def get_author_profile(author_id: str) -> dict:
    """Read profile basics on the coordinator using the shared Chrome window."""
    driver = get_driver()
    time.sleep(random.uniform(1, 5))
    url = 'https://scholar.google.com/citations?' + urlencode({'user': author_id, 'hl': 'en'})
    html = _load_scholar_page(driver, url, 'gsc_prf_in')
    return parse_author_profile(html, url)


def parse_author_profile(html, url):
    """Use the same profile parser for browser and HTTP responses."""
    soup = BeautifulSoup(html, 'html.parser')
    name = soup.find(id='gsc_prf_in')
    if name is None:
        raise RuntimeError(
            f'Cannot read Google Scholar profile {url}. The page may be blocked or unavailable. '
            'Resolve access in the browser and rerun; completed profiles are cached.')
    # Keep the subset of scholarly-style fields consumed by citation_map.py.
    # organization is the linked Scholar organization ID, not the free-text
    # affiliation; the conservative path resolves its official name separately.
    author = {'name': name.get_text(strip=True)}
    affiliation = soup.find('div', class_='gsc_prf_il')
    if affiliation is not None:
        author['affiliation'] = affiliation.get_text(' ', strip=True)
        for link in affiliation.find_all('a', href=True):
            organization = parse_qs(urlparse(link['href']).query).get('org')
            if organization:
                author['organization'] = organization[0]
                break
    return author


class ProfileNeedsBrowser(RuntimeError):
    """An HTTP profile request needs the coordinator's visible browser."""


def get_author_profile_http(author_id, browser_context, paused, stopped):
    """Fetch one profile without Selenium or terminal prompts in the worker."""
    if stopped.wait(random.uniform(1, 5)) or paused.is_set():
        return None  # Deferred: no new request while a challenge is pending.
    cookies, user_agent = browser_context
    # Each request gets an independent cookie jar. Domain/path/expiry rules are
    # preserved rather than sharing mutable cookie state across worker threads.
    jar = CookieJar()
    for cookie in cookies:
        domain = cookie.get('domain', 'scholar.google.com')
        jar.set_cookie(Cookie(
            version=0, name=cookie['name'], value=cookie['value'], port=None,
            port_specified=False, domain=domain, domain_specified=True,
            domain_initial_dot=domain.startswith('.'), path=cookie.get('path', '/'),
            path_specified=True, secure=cookie.get('secure', False),
            expires=int(cookie['expiry']) if cookie.get('expiry') else None,
            discard=not bool(cookie.get('expiry')), comment=None, comment_url=None,
            rest={}, rfc2109=False))
    opener = build_opener(HTTPCookieProcessor(jar))
    url = 'https://scholar.google.com/citations?' + urlencode({'user': author_id, 'hl': 'en'})
    request = Request(url, headers={'User-Agent': user_agent, 'Accept-Language': 'en-US,en;q=0.9'})
    try:
        with opener.open(request, timeout=15) as response:
            html = response.read().decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
        return parse_author_profile(html, url)
    except (HTTPError, URLError, TimeoutError, RuntimeError) as error:
        # Missing profile markup can mean CAPTCHA, a block, or an unavailable
        # page. Do not record that as an author with no affiliation: let Chrome
        # try the same profile, and propagate failure if it cannot read it either.
        paused.set()
        raise ProfileNeedsBrowser(f'{author_id}: {error}') from error


def iter_author_profiles(author_ids, num_processes=8):
    """Yield profiles on the caller thread; HTTP workers never operate Chrome.

    Requests run in bounded batches. A challenge pauses new requests; in-flight
    requests finish before the single browser handles manual verification.
    Repeated HTTP rejection switches the remainder to sequential browser reads.
    """
    if isinstance(num_processes, bool) or not isinstance(num_processes, int) or num_processes < 1:
        raise ValueError('num_processes must be a positive integer')
    pending = deque(author_ids)
    if not pending:
        return
    # Establish browser cookies and verify access before sending concurrent HTTP requests.
    first = pending.popleft()
    yield first, get_author_profile(first)
    if not pending:
        return
    if num_processes == 1:
        for author_id in pending:
            yield author_id, get_author_profile(author_id)
        return

    stopped = threading.Event()
    # Keep the public num_processes option, but use lightweight threads for HTTP
    # I/O. This worker count does not create Chrome processes or browser tabs.
    pool = ThreadPoolExecutor(max_workers=num_processes, thread_name_prefix='profile-http')
    blocked_batches = 0
    try:
        while pending:
            # Cookie transfer does not guarantee HTTP access. After two batches
            # with failures and no HTTP successes, stop retrying that transport.
            if blocked_batches >= 2:
                tqdm.write('[INFO] HTTP access is still failing after browser verification. '
                      'Using the same Chrome window sequentially for remaining profiles.')
                for author_id in pending:
                    yield author_id, get_author_profile(author_id)
                return
            driver = get_driver()
            # Take a fresh snapshot after any manual browser verification. Workers
            # receive this data, never the WebDriver instance itself.
            context = (driver.get_cookies(), driver.execute_script('return navigator.userAgent'))
            paused = threading.Event()
            batch = [pending.popleft() for _ in range(min(num_processes, len(pending)))]
            futures = {pool.submit(get_author_profile_http, author_id, context, paused, stopped): author_id
                       for author_id in batch}
            completed, browser_required, deferred = [], [], []
            for future in as_completed(futures):
                author_id = futures[future]
                try:
                    profile = future.result()
                except ProfileNeedsBrowser as error:
                    tqdm.write('[INFO] HTTP lookup needs the shared browser: %s' % error)
                    browser_required.append(author_id)
                else:
                    if profile is None:
                        deferred.append(author_id)
                    else:
                        completed.append((author_id, profile))
            # Drain the bounded batch before yielding: the caller may use Chrome
            # for conservative organization lookup as well as checkpoint results.
            # This also prevents HTTP requests during a manual CAPTCHA prompt.
            for result in completed:
                yield result
            if browser_required:
                blocked_batches = blocked_batches + 1 if not completed else 0
                tqdm.write('[INFO] HTTP workers paused. Resolve any challenges in the shared Chrome window.')
                for author_id in browser_required:
                    yield author_id, get_author_profile(author_id)
            else:
                blocked_batches = 0
            pending.extendleft(reversed(deferred))
    finally:
        stopped.set()
        pool.shutdown(wait=True, cancel_futures=True)

def get_html_per_citation_page(soup) -> List[Tuple[str, str]]:
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
                tqdm.write("[WARNING!] Could not find author links for %s" % title)
                citing_authors_and_citing_papers.append((NO_AUTHOR_FOUND_STR, title))
        else:
            continue
    return citing_authors_and_citing_papers


def get_publication_citation_links(scholar_id: str) -> List[Tuple[str, str]]:
    """Read every profile publication page and its citing-results links in Chrome."""
    driver = get_driver()
    publications = []
    seen = set()
    seen_pages = set()
    start = 0
    while True:
        url = 'https://scholar.google.com/citations?' + urlencode({
            'user': scholar_id, 'hl': 'en', 'cstart': start, 'pagesize': 100})
        time.sleep(random.uniform(1, 5))
        html = _load_scholar_page(driver, url, 'gsc_prf_in')
        soup = BeautifulSoup(html, 'html.parser')
        if soup.find(id='gsc_prf_in') is None or soup.find(id='gsc_a_b') is None:
            raise RuntimeError(f'Cannot read publications from {url}. '
                               'The page may be blocked or unavailable; check the Chrome window.')
        rows = soup.select('#gsc_a_b tr.gsc_a_tr')
        if not rows:
            break
        page_signature = tuple(
            (row.select_one('a.gsc_a_at').get('href', ''),
             row.select_one('a.gsc_a_at').get_text(' ', strip=True))
            for row in rows if row.select_one('a.gsc_a_at') is not None)
        if page_signature in seen_pages:
            raise RuntimeError(f'Publication pagination repeated a page at {url}. '
                               'Stopping to avoid silently truncating the publication list.')
        seen_pages.add(page_signature)
        for row in rows:
            title = row.select_one('a.gsc_a_at')
            citations = row.select_one('a.gsc_a_ac')
            if title is None:
                raise RuntimeError(f'Cannot parse a publication title on {url}.')
            if citations is None or not citations.get_text(strip=True):
                continue  # Publications without citations need no citing-results request.
            href = citations.get('href', '')
            if not parse_qs(urlparse(href).query).get('cites'):
                raise RuntimeError(f'Cannot parse the citation link for {title.get_text(strip=True)}.')
            citation_url = 'https://scholar.google.com' + href if href.startswith('/') else href
            entry = (citation_url, title.get_text(' ', strip=True))
            if entry not in seen:
                seen.add(entry)
                publications.append(entry)
        next_button = soup.find(id='gsc_bpf_more') or soup.find(id='gsc_bpf_next')
        if next_button is not None and (next_button.has_attr('disabled') or
                                       next_button.get('aria-disabled') == 'true'):
            break
        # If pagination controls are absent, probe the next offset until an empty
        # publication table confirms the end. Advance by the actual row count in
        # case Scholar returned fewer than the requested 100 entries.
        start += len(rows)
    return publications


def get_citing_author_ids_and_citing_papers(
    paper_url: str,
    progress_callback: Optional[Callable[[int], None]] = None,
    page_cache_folder: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """Read author IDs and paper titles from all pages of a publication's citations.

    paper_url is the "cited by" results URL for the publication being cited.
    All navigation stays in the shared Chrome window for manual CAPTCHA handling.
    The optional callback updates the caller's progress bar before each page load.
    With page_cache_folder, every parsed page and its next link are saved before
    proceeding. Reruns follow that saved chain without requesting completed pages.
    """
    driver = None  # Entirely cached citation lists do not need to open Chrome.
    results = []
    visited_urls = set()
    current_url = paper_url
    current_page_number = 1
    cached_pages = 0
    while current_url:
        # A malformed or repeated next link must not cause an infinite loop or a
        # successful-looking, incomplete citation cache.
        if current_url in visited_urls:
            raise RuntimeError(f'Citation pagination repeated a page: {current_url}')
        visited_urls.add(current_url)
        cache_path = (os.path.join(page_cache_folder,
                                  hashlib.sha256(current_url.encode('utf-8')).hexdigest() + '.json')
                      if page_cache_folder else None)
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, encoding='utf-8') as saved:
                page = json.load(saved)
            if page.get('version') != 1 or page.get('url') != current_url:
                raise RuntimeError('Unrecognized citation-page checkpoint: %s' % cache_path)
            results.extend(tuple(entry) for entry in page['results'])
            current_url = page['next_url']
            current_page_number += 1
            cached_pages += 1
            continue
        if cached_pages:
            tqdm.write('[INFO] Reused %d saved citing-results pages; resuming at page %d.' % (
                cached_pages, current_page_number))
            cached_pages = 0
        if driver is None:
            driver = get_driver()
        time.sleep(random.uniform(1, 5))
        if progress_callback is not None:
            progress_callback(current_page_number)
        tqdm.write('[INFO] Reading citing-results page %d: %s' % (current_page_number, current_url))
        html = _load_scholar_page(driver, current_url, 'gs_res_ccl')
        soup = BeautifulSoup(html, 'html.parser')
        # An unrecognized error page is not evidence that there are no citations.
        if soup.find(id='gs_res_ccl') is None:
            raise RuntimeError(f'Cannot read citation results at {current_url}. '
                               'Check the shared Chrome window before rerunning.')
        page_results = get_html_per_citation_page(soup)

        # Read navigation from the page we just loaded, not the original page.
        # Scholar's visible page-number links change as we advance through results.
        next_link = next((link for link in soup.select('a.gs_nma[href]')
                          if link.get_text(strip=True) == str(current_page_number + 1)), None)
        if next_link is None:
            # Some layouts expose a Next arrow instead of a numbered link.
            arrow = soup.select_one('#gs_n a[href] .gs_ico_nav_next')
            next_link = arrow.find_parent('a') if arrow is not None else None
        next_url = urljoin(current_url, next_link['href']) if next_link is not None else None
        if next_url in visited_urls:
            raise RuntimeError(f'Citation pagination repeated a page: {next_url}')
        if cache_path:
            # Write a separate file per page, including the final page. Replacing
            # it atomically prevents an interrupted write from looking complete.
            os.makedirs(page_cache_folder, exist_ok=True)
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                                 dir=page_cache_folder, delete=False) as saved:
                    temporary_path = saved.name
                    json.dump({'version': 1, 'url': current_url,
                               'results': page_results, 'next_url': next_url}, saved)
                os.replace(temporary_path, cache_path)
            finally:
                if temporary_path and os.path.exists(temporary_path):
                    os.unlink(temporary_path)
        results.extend(page_results)
        current_url = next_url
        current_page_number += 1
    if cached_pages:
        tqdm.write('[INFO] Reused %d saved citing-results pages; this publication is complete.' % cached_pages)
    return results


def get_organization_name(organization_id: str) -> str:
    '''
    Get the official name of the organization defined by the unique Google Scholar organization ID.
    '''

    driver = get_driver()
    url = f'https://scholar.google.com/citations?view_op=view_org&org={organization_id}&hl=en'

    # One delay per navigation is sufficient; avoid sleeping twice for one page.
    time.sleep(random.uniform(1, 5))
    html = _load_scholar_page(driver, url, 'gsc_authors_header')

    soup = BeautifulSoup(html, 'html.parser')
    tag = soup.find('h2', {'class': 'gsc_authors_header'})
    if not tag:
        raise Exception(f'When getting organization name, failed to parse {url}.')
    return tag.text.replace('Learn more', '').strip()
