# Copyright (c) 2024 Chen Liu
# All rights reserved.
import json
import os
import pickle
import random
import re
import time
from functools import partial
from typing import Any, List, Optional, Tuple, Union

import folium
import pandas as pd
import pycountry
from geopy.adapters import RequestsAdapter
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from tqdm import tqdm

from .scholarly_support import (
    KNOWN_AFFILIATION_DICT,
    NO_AUTHOR_FOUND_STR,
    get_author_profile,
    get_citing_author_ids_and_citing_papers,
    get_organization_name,
    get_publication_citation_links,
    iter_author_profiles,
)

# Name the existing tuple layouts without changing the cache or CSV formats.
# The first field is a Scholar ID during discovery and a name after profile lookup.
CitingAuthorPaper = Tuple[str, str, str]
AuthorPaperAffiliation = Tuple[str, str, str, str]
# CSV reloads can represent missing fields as NaN, while fresh rows use empty strings.
LocationValue = Union[str, float, None]
GeocodedCitation = Tuple[
    str, str, str, str,
    LocationValue, LocationValue, LocationValue,
    LocationValue, LocationValue, LocationValue,
]
KnownAffiliation = Tuple[str, str, str, str, float, float]


def find_all_citing_authors(scholar_id: str) -> List[CitingAuthorPaper]:
    '''
    Step 1. Find all publications of the given Google Scholar ID.
    Step 2. Find all citing authors.
    '''
    # Previously this used scholarly.search_author_id(), scholarly.fill(author),
    # and scholarly.fill(publication) to obtain citation IDs. Read titles and
    # "cited by" links directly from Chrome instead: the manual CAPTCHA flow is
    # then visible, and separate publication-metadata requests are unnecessary.
    # Discovery stays sequential because it uses the shared browser.
    publications = get_publication_citation_links(scholar_id)
    print('Found %d publication citation links.\n' % len(publications))
    entries = []
    for citation_url, cited_title in tqdm(publications, desc='Finding citing authors and papers',
                                          total=len(publications)):
        for author_id, citing_title in get_citing_author_ids_and_citing_papers(citation_url):
            entries.append((author_id, citing_title, cited_title))
    return entries

def find_all_citing_affiliations(all_citing_author_paper_tuple_list: List[CitingAuthorPaper],
                                 num_processes: int = 8,
                                 affiliation_conservative: bool = False,
                                 progress_cache_path: Optional[str] = None) -> List[AuthorPaperAffiliation]:
    """Find affiliations with HTTP workers and one shared CAPTCHA browser.

    num_processes controls HTTP concurrency, not the number of Chrome windows.
    Successful lookups (including profiles without affiliations) are checkpointed.
    Failed lookups stop the run and remain eligible for retry on the next run.
    """
    lookup = (__affiliations_from_authors_conservative if affiliation_conservative
              else __affiliations_from_authors_aggressive)
    profiles = load_cache(progress_cache_path) if progress_cache_path and os.path.exists(progress_cache_path) else {}
    # One author can cite several publications. Fetch the profile once, then
    # restore every author/citing-paper/cited-paper relationship below.
    author_ids = list(dict.fromkeys(entry[0] for entry in all_citing_author_paper_tuple_list))
    pending = [author_id for author_id in author_ids
               if author_id != NO_AUTHOR_FOUND_STR and author_id not in profiles]
    print('Affiliations: %d cached, %d remaining; up to %d HTTP workers, one Chrome window.' % (
        len(author_ids) - len(pending), len(pending), num_processes))
    profile_iterator = iter_author_profiles(pending, num_processes=num_processes)
    try:
        for author_id, profile in tqdm(profile_iterator, total=len(pending),
                                       desc='Finding affiliations for unique citing authors'):
            # The coordinator receives both HTTP and browser results through the
            # same parser. Passing the profile avoids a second network lookup.
            # Conservative organization-name lookups also stay on this thread,
            # so Selenium and terminal prompts never run inside HTTP workers.
            result = lookup((author_id, '', ''), citing_author=profile)
            profiles[author_id] = (result[0], result[3]) if result else None
            if progress_cache_path:
                save_cache(profiles, progress_cache_path)
    finally:
        # Also stop HTTP workers if organization lookup, cache writing, or Ctrl+C
        # interrupts the consumer before the profile iterator is exhausted.
        profile_iterator.close()

    entries = []
    for author_id, citing_paper, cited_paper in all_citing_author_paper_tuple_list:
        if author_id == NO_AUTHOR_FOUND_STR:
            entries.append((NO_AUTHOR_FOUND_STR, citing_paper, cited_paper, NO_AUTHOR_FOUND_STR))
        elif profiles[author_id] is not None:
            name, affiliation = profiles[author_id]
            entries.append((name, citing_paper, cited_paper, affiliation))
    return entries

def clean_affiliation_names(author_paper_affiliation_tuple_list: List[AuthorPaperAffiliation]) -> List[AuthorPaperAffiliation]:
    '''
    Optional Step. Clean up the names of affiliations from the authors' affiliation tab on their Google Scholar profiles.
    NOTE: This logic is very naive. Please send an issue or pull request if you have any idea how to improve it.
    Currently we will not consider any paid service or tools that pose extra burden on the users, such as GPT API.
    '''
    cleaned_author_paper_affiliation_tuple_list = []
    for author_name, citing_paper_title, cited_paper_title, affiliation_string in author_paper_affiliation_tuple_list:
        if author_name == NO_AUTHOR_FOUND_STR:
            cleaned_author_paper_affiliation_tuple_list.append((NO_AUTHOR_FOUND_STR, citing_paper_title, cited_paper_title, NO_AUTHOR_FOUND_STR))
        else:
            # Use a regular expression to split the string by ';' or 'and'.
            substring_list = [part.strip() for part in re.split(r'[;]|\band\b', affiliation_string)]
            # Further split the substrings by ',' if the latter component is not a country.
            substring_list = __country_aware_comma_split(substring_list)

            for substring in substring_list:
                # Use a regular expression to remove anything before 'at', or '@'.
                cleaned_affiliation = re.sub(r'.*?\bat\b|.*?@', '', substring, flags=re.IGNORECASE).strip()
                # Use a regular expression to filter out strings that represent
                # a person's identity rather than affiliation.
                is_common_identity_string = re.search(
                    re.compile(
                        r'\b(director|manager|chair|engineer|programmer|scientist|professor|lecturer|phd|ph\.d|postdoc|doctor|student|department of)\b',
                        re.IGNORECASE),
                    cleaned_affiliation)
                if not is_common_identity_string:
                    cleaned_author_paper_affiliation_tuple_list.append((author_name, citing_paper_title, cited_paper_title, cleaned_affiliation))
    return cleaned_author_paper_affiliation_tuple_list

def fill_known_affiliations(affiliation_name: str) -> Optional[KnownAffiliation]:
    '''
    If the affiliation is known, return its geolocation.
    If not, return None.
    The reason we have this function is taht geolocator may return hilarious results,
    such as putting the company Amazon in Amazon rain forest.
    NOTE: This is a temporal fix. Can be replaced by smarter natural language parsers.
    '''
    for key in KNOWN_AFFILIATION_DICT:
        if key in affiliation_name.lower():
            return KNOWN_AFFILIATION_DICT[key]
    return None

def affiliation_invalid(affiliation_name: str) -> bool:
    '''
    Check if the affiliation is invalid.
    Typical invalid affiliation contains non-affiliation words, such as 'computer science'.
    Invalid affiliations will waste time in geolocator.geocode(affiliation_name).
    NOTE: This is a temporal fix. Can be replaced by smarter natural language parsers.
    '''
    invalid_affiliation_set = {
        NO_AUTHOR_FOUND_STR.lower(),
        'computer', 'computer science', 'electrical', 'engineering', 'researcher',
        'scholar', 'inc.', 'school', 'department', 'student', 'candidate', 'professor', 'faculty', 'associate'
    }
    for key in invalid_affiliation_set:
        if key in affiliation_name.lower():
            return True
    return False

def affiliation_text_to_geocode(author_paper_affiliation_tuple_list: List[AuthorPaperAffiliation],
                                max_attempts: int = 3,
                                progress_cache_path: Optional[str] = None) -> List[GeocodedCitation]:
    """Geocode unique affiliations sequentially, caching each completed lookup.

    Ctrl+C propagates normally. Transient failures are retried but not cached;
    unresolved entries remain in the CSV with empty location fields.
    """
    if not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError('max_attempts must be a positive integer')
    cached = load_cache(progress_cache_path) if progress_cache_path and os.path.exists(progress_cache_path) else {}
    affiliation_map = {}
    for entry in author_paper_affiliation_tuple_list:
        affiliation_map.setdefault(entry[3], []).append(entry)

    coordinates_and_info = []
    num_located_affiliations = 0
    # Disable hidden transport retries; keep all retries explicit and interruptible.
    with Nominatim(user_agent='citation-map (https://github.com/ChenLiu-1996/CitationMap)',
                   timeout=10, adapter_factory=partial(RequestsAdapter, max_retries=0)) as geolocator:
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1,
                              max_retries=0, swallow_exceptions=False)
        for affiliation_name, entries in tqdm(affiliation_map.items(),
                                              desc='Finding geographic coordinates for unique affiliations',
                                              total=len(affiliation_map)):
            key = ' '.join(affiliation_name.split()).casefold()
            fields = None
            if affiliation_invalid(affiliation_name):
                pass
            elif fill_known_affiliations(affiliation_name) is not None:
                county, city, state, country, latitude, longitude = fill_known_affiliations(affiliation_name)
                fields = (latitude, longitude, county, city, state, country)
            elif key in cached:
                fields = cached[key]
            else:
                for attempt in range(max_attempts):
                    try:
                        location = geocode(affiliation_name, addressdetails=True, language='en')
                    except (GeocoderTimedOut, GeocoderUnavailable) as error:
                        tqdm.write('Geocoding attempt %d/%d failed for %s: %s' % (
                            attempt + 1, max_attempts, affiliation_name, error))
                        if attempt + 1 < max_attempts:
                            time.sleep(2 ** attempt)
                        continue
                    # Address details in the forward response eliminate a reverse request.
                    if location is not None:
                        address = location.raw.get('address', {})
                        fields = (location.latitude, location.longitude, address.get('county', ''),
                                  address.get('city') or address.get('town') or address.get('village', ''),
                                  address.get('state', ''), address.get('country', ''))
                    cached[key] = fields  # Also remember successful queries with no match.
                    if progress_cache_path:
                        save_cache(cached, progress_cache_path)
                    break
            if fields is not None:
                num_located_affiliations += 1
            else:
                fields = ('', '', '', '', '', '')
            coordinates_and_info.extend(tuple(entry) + tuple(fields) for entry in entries)
    print('\nConverted %d/%d affiliations to Geocodes.' % (
        num_located_affiliations, len(affiliation_map)))
    return coordinates_and_info

def export_dict_to_csv(coordinates_and_info: List[GeocodedCitation], csv_output_path: str) -> None:
    '''
    Step 5.1: Export csv file recording citation information.
    '''

    citation_df = pd.DataFrame(coordinates_and_info,
                               columns=['citing author name', 'citing paper title', 'cited paper title',
                                        'affiliation', 'latitude', 'longitude',
                                        'county', 'city', 'state', 'country'])

    citation_df.to_csv(csv_output_path)
    return

def read_csv_to_dict(csv_path: str) -> List[GeocodedCitation]:
    '''
    Step 5.1: Read csv file recording citation information.
    Used when `parse_csv` is True. Returns tuple rows, despite the legacy function name.
    '''

    citation_df = pd.read_csv(csv_path, index_col=0)
    coordinates_and_info = list(citation_df.itertuples(index=False, name=None))
    return coordinates_and_info

def create_map(coordinates_and_info: List[GeocodedCitation], pin_colorful: bool = True) -> folium.Map:
    '''
    Step 5.2: Create the Citation World Map.

    For authors under the same affiliations, they will be displayed in the same pin.
    '''
    # Embed public-domain Natural Earth geometry instead of requesting remote
    # raster tiles. Directly opened HTML files may lack the Referer required by
    # tile providers, which can produce a 403 image behind otherwise valid pins.
    # Keep this data bundled in the wheel/sdist: generation must not download it.
    citation_map = folium.Map(location=[20, 0], zoom_start=2, tiles=None)
    citation_map.get_root().header.add_child(folium.Element(
        '<style>.leaflet-container { background: #dcecf4; }</style>'))
    with open(os.path.join(os.path.dirname(__file__), 'world_countries.geojson'),
              encoding='utf-8') as source:
        countries = json.load(source)
    folium.GeoJson(
        countries,
        name='World countries',
        style_function=lambda _feature: {
            'fillColor': '#f6f3eb', 'color': '#98a6af',
            'weight': 0.6, 'fillOpacity': 1,
        },
        tooltip=folium.GeoJsonTooltip(fields=['name'], labels=False),
        attribution='Made with <a href="https://www.naturalearthdata.com/">Natural Earth</a>',
    ).add_to(citation_map)

    # Group rows once. Both pin styles share the same location checks and popup
    # construction; only the optional icon color differs.
    affiliation_map = {}
    for entry in coordinates_and_info:
        affiliation_name = entry[3]
        if affiliation_name != NO_AUTHOR_FOUND_STR:
            affiliation_map.setdefault(affiliation_name, []).append(entry)

    colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred',
              'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue',
              'darkpurple', 'pink', 'lightblue', 'lightgreen',
              'gray', 'black', 'lightgray']
    for affiliation_name, entries in affiliation_map.items():
        # A manually edited CSV may contain blank or NaN coordinates. Preserve
        # the existing rule: do not draw a group if any of its rows lacks a location.
        if any(pd.isna(entry[4]) or pd.isna(entry[5]) or entry[4] == '' or entry[5] == ''
               for entry in entries):
            continue
        author_names = [entry[0] for entry in entries]
        latitude, longitude = entries[-1][4:6]
        icon = folium.Icon(color=random.choice(colors)) if pin_colorful else None
        folium.Marker(
            [latitude, longitude],
            popup='%s (%s)' % (affiliation_name, ' & '.join(author_names)),
            icon=icon,
        ).add_to(citation_map)
    return citation_map


def count_citation_stats(coordinates_and_info: List[GeocodedCitation]) -> Tuple[int, int, int]:
    """Count distinct authors, affiliations, and countries in the output rows."""
    unique_authors, unique_affiliations, unique_countries = set(), set(), set()
    for author_name, _, _, affiliation_name, _, _, _, _, _, country in coordinates_and_info:
        if affiliation_name == NO_AUTHOR_FOUND_STR:
            continue
        unique_authors.add(author_name)
        unique_affiliations.add(affiliation_name)
        unique_countries.add(country)
    # Count after the loop so empty or entirely unidentified results return zeros.
    return len(unique_authors), len(unique_affiliations), len(unique_countries)


def __affiliations_from_authors_conservative(
    citing_author_paper_info: CitingAuthorPaper,
    citing_author: Optional[dict] = None,
) -> Optional[AuthorPaperAffiliation]:
    '''
    Conservative: only use Google Scholar verified organization.
    This will have higher precision and lower recall.
    '''
    citing_author_id, citing_paper_title, cited_paper_title = citing_author_paper_info
    if citing_author_id == NO_AUTHOR_FOUND_STR:
        return (NO_AUTHOR_FOUND_STR, citing_paper_title, cited_paper_title, NO_AUTHOR_FOUND_STR)

    # This replaces scholarly.search_author_id(). The main pipeline supplies an
    # already-fetched profile; direct helper calls use the shared Chrome window.
    if citing_author is None:
        citing_author = get_author_profile(citing_author_id)

    if 'organization' in citing_author:
        author_organization = get_organization_name(citing_author['organization'])
        return (citing_author['name'], citing_paper_title, cited_paper_title, author_organization)
    return None

def __affiliations_from_authors_aggressive(
    citing_author_paper_info: CitingAuthorPaper,
    citing_author: Optional[dict] = None,
) -> Optional[AuthorPaperAffiliation]:
    '''
    Aggressive: use the self-reported affiliation string from the Google Scholar affiliation panel.
    This will have lower precision and higher recall.
    '''
    citing_author_id, citing_paper_title, cited_paper_title = citing_author_paper_info
    if citing_author_id == NO_AUTHOR_FOUND_STR:
        return (NO_AUTHOR_FOUND_STR, citing_paper_title, cited_paper_title, NO_AUTHOR_FOUND_STR)

    # Preserve the self-reported affiliation text; the fetching transport changed,
    # while aggressive affiliation selection still uses this same profile field.
    if citing_author is None:
        citing_author = get_author_profile(citing_author_id)
    if 'affiliation' in citing_author:
        return (citing_author['name'], citing_paper_title, cited_paper_title, citing_author['affiliation'])
    return None

def __country_aware_comma_split(string_list: List[str]) -> List[str]:
    comma_split_list = []

    for part in string_list:
        # Split the strings by comma.
        # NOTE: The non-English comma is entered intentionally.
        sub_parts = [sub_part.strip() for sub_part in re.split(r'[,，]', part)]
        sub_parts_iter = iter(sub_parts)

        # Merge the split strings if the latter component is a country name.
        for sub_part in sub_parts_iter:
            if __iscountry(sub_part):
                continue  # Skip country names if they appear as the first sub_part.
            next_part = next(sub_parts_iter, None)
            if __iscountry(next_part):
                comma_split_list.append(f"{sub_part}, {next_part}")
            else:
                comma_split_list.append(sub_part)
                if next_part:
                    comma_split_list.append(next_part)
    return comma_split_list

def __iscountry(string: str) -> bool:
    try:
        pycountry.countries.lookup(string)
        return True
    except LookupError:
        return False

def __print_author_and_affiliation(author_paper_affiliation_tuple_list: List[AuthorPaperAffiliation]) -> None:
    __author_affiliation_tuple_list = []
    for author_name, _, _, affiliation_name in sorted(author_paper_affiliation_tuple_list):
        if author_name == NO_AUTHOR_FOUND_STR:
            continue
        __author_affiliation_tuple_list.append((author_name, affiliation_name))

    # Take unique tuples.
    __author_affiliation_tuple_list = list(set(__author_affiliation_tuple_list))
    for author_name, affiliation_name in sorted(__author_affiliation_tuple_list):
        print('Author: %s. Affiliation: %s.' % (author_name, affiliation_name))
    print('')
    return


def save_cache(data: Any, fpath: str) -> None:
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    temporary_path = fpath + ".tmp"
    with open(temporary_path, "wb") as fd:
        pickle.dump(data, fd)
    os.replace(temporary_path, fpath)

def load_cache(fpath: str) -> Any:
    with open(fpath, "rb") as fd:
        return pickle.load(fd)

def generate_citation_map(scholar_id: str,
                          output_path: str = 'citation_map.html',
                          csv_output_path: str = 'citation_info.csv',
                          parse_csv: bool = False,
                          cache_folder: str = 'cache',
                          affiliation_conservative: bool = False,
                          num_processes: int = 8,
                          pin_colorful: bool = True,
                          print_citing_affiliations: bool = True):
    '''
    Google Scholar Citation World Map.

    Parameters
    ----
    scholar_id: str
        Your Google Scholar ID.
    output_path: str
        (default is 'citation_map.html')
        The path to the output HTML file.
    csv_output_path: str
        (default is 'citation_info.csv')
        The path to the output csv file.
    parse_csv: bool
        (default is False)
        If True, will directly jump to Step 5.2, using the information loaded from the csv.
    cache_folder: str
        (default is 'cache')
        The folder to save intermediate results, after finding (author, paper) but before finding the affiliations.
        This is because the user might want to try the aggressive vs. conservative approach.
        Set to None if you do not want caching.
    affiliation_conservative: bool
        (default is False)
        If true, we will use a more conservative approach to identify affiliations.
        If false, we will use a more aggressive approach to identify affiliations.
    num_processes: int
        (default is 8)
        Maximum concurrent HTTP affiliation lookups, with one shared CAPTCHA browser.
        Setting 1 uses sequential browser lookups. Discovery and geocoding remain sequential.
    pin_colorful: bool
        (default is True)
        If true, the location pins will have a variety of colors.
        Otherwise, it will only have one color.
    print_citing_affiliations: bool
        (default is True)
        If true, print the list of citing affiliations (affiliations of citing authors).
    '''

    if not parse_csv:

        if cache_folder is not None:
            cache_path = os.path.join(cache_folder, scholar_id, 'all_citing_author_paper_tuple_list.pkl')
        else:
            cache_path = None

        if cache_path is None or not os.path.exists(cache_path):
            print('No cache found for this author. Finding citing authors from scratch.\n')

            # NOTE: Step 1. Find all publications of the given Google Scholar ID.
            #       Step 2. Find all citing authors.
            all_citing_author_paper_tuple_list = find_all_citing_authors(scholar_id=scholar_id)
            print('A total of %d citing authors recorded.\n' % len(all_citing_author_paper_tuple_list))
            if cache_path is not None and len(all_citing_author_paper_tuple_list) > 0:
                save_cache(all_citing_author_paper_tuple_list, cache_path)
            print('Saved to cache: %s.\n' % cache_path)

        else:
            print('Cache found. Loading author paper information from cache.\n')
            all_citing_author_paper_tuple_list = load_cache(cache_path)
            print('Loaded from cache: %s.\n' % cache_path)
            print('A total of %d citing authors loaded.\n' % len(all_citing_author_paper_tuple_list))

        if cache_folder is not None:
            cache_path = os.path.join(cache_folder, scholar_id,
                                      'author_paper_affiliation_%s.pkl' % (
                                          'conservative' if affiliation_conservative else 'aggressive'))
        else:
            cache_path = None

        if cache_path is None or not os.path.exists(cache_path):
            print('No cache found for this author. Finding citing affiliations from scratch.\n')

            # NOTE: Step 2. Find all citing affiliations.
            print('Identifying affiliations using the %s approach.' % ('conservative' if affiliation_conservative else 'aggressive'))
            author_paper_affiliation_tuple_list = find_all_citing_affiliations(all_citing_author_paper_tuple_list,
                                                                            num_processes=num_processes,
                                                                            affiliation_conservative=affiliation_conservative,
                                                                            progress_cache_path=cache_path + ".profiles" if cache_path else None)
            print('\nA total of %d citing affiliations recorded.\n' % len(author_paper_affiliation_tuple_list))
            # Take unique tuples.
            author_paper_affiliation_tuple_list = list(set(author_paper_affiliation_tuple_list))

            # NOTE: Step 3. Clean the affiliation strings (optional, only used if taking the aggressive approach).
            if print_citing_affiliations:
                if affiliation_conservative:
                    print('Taking the conservative approach. Will not need to clean the affiliation names.')
                    print('List of all citing authors and affiliations:\n')
                else:
                    print('Taking the aggressive approach. Cleaning the affiliation names.')
                    print('List of all citing authors and affiliations before cleaning:\n')
                __print_author_and_affiliation(author_paper_affiliation_tuple_list)
            if not affiliation_conservative:
                cleaned_author_paper_affiliation_tuple_list = clean_affiliation_names(author_paper_affiliation_tuple_list)
                if print_citing_affiliations:
                    print('List of all citing authors and affiliations after cleaning:\n')
                    __print_author_and_affiliation(cleaned_author_paper_affiliation_tuple_list)
                # Use the merged set to maximize coverage.
                author_paper_affiliation_tuple_list += cleaned_author_paper_affiliation_tuple_list
                # Take unique tuples.
                author_paper_affiliation_tuple_list = list(set(author_paper_affiliation_tuple_list))

            if cache_path is not None and len(author_paper_affiliation_tuple_list) > 0:
                save_cache(author_paper_affiliation_tuple_list, cache_path)
            print('Saved to cache: %s.\n' % cache_path)

        else:
            print('Cache found. Loading author paper and affiliation information from cache.\n')
            author_paper_affiliation_tuple_list = load_cache(cache_path)
            print('List of all citing authors and affiliations loaded:\n')
            __print_author_and_affiliation(author_paper_affiliation_tuple_list)

        # NOTE: Step 4. Convert affiliations in plain text to Geocode.
        geocode_cache_path = os.path.join(cache_folder, 'geocodes_v1.pkl') if cache_folder is not None else None
        coordinates_and_info = affiliation_text_to_geocode(
            author_paper_affiliation_tuple_list, progress_cache_path=geocode_cache_path)
        # Take unique tuples.
        coordinates_and_info = sorted(list(set(coordinates_and_info)))

        # NOTE: Step 5.1. Export csv file recording citation information.
        export_dict_to_csv(coordinates_and_info, csv_output_path)
        print('\nCitation information exported to %s.' % csv_output_path)

    else:
        print('\nDirectly parsing the csv. Skipping all previous steps.')
        assert os.path.isfile(csv_output_path), '`csv_output_path` is not a file.'
        coordinates_and_info = read_csv_to_dict(csv_output_path)
        print('\nCitation information loaded from %s.' % csv_output_path)

    # NOTE: Step 5.2. Create the citation world map.
    citation_map = create_map(coordinates_and_info, pin_colorful=pin_colorful)
    citation_map.save(output_path)
    print('\nHTML map created and saved at %s.\n' % output_path)

    num_authors, num_affiliations, num_countries = count_citation_stats(coordinates_and_info)
    print('\nYou have been cited by %s researchers from %s affiliations and %s countries.\n' % (
        num_authors, num_affiliations, num_countries))
    return


if __name__ == '__main__':
    # Replace this with your Google Scholar ID.
    scholar_id = '3rDjnykAAAAJ'
    generate_citation_map(scholar_id,
                          output_path='citation_map.html',
                          csv_output_path='citation_info.csv',
                          parse_csv=False,
                          cache_folder='cache',
                          affiliation_conservative=True,
                          num_processes=8,
                          pin_colorful=True,
                          print_citing_affiliations=True)
