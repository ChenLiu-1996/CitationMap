import re
import random
import time
import itertools

from typing import List, Tuple
from scholarly import scholarly, ProxyGenerator
from geopy.geocoders import Nominatim

import folium
from tqdm import tqdm
from multiprocessing import Pool

from .scholarly_support import get_author_ids


def fetch_google_scholar_profile(scholar_id: str):
    '''
    Step 1: Fetch Google Scholar Profile using Scholar ID.
    '''
    author = scholarly.search_author_id(scholar_id)
    author = scholarly.fill(author, sections=['publications'])
    return author

def find_all_citing_institutions(publications, num_processes: int = 16) -> List[Tuple[str]]:
    '''
    Step 2. Find all citing institutions (i.e., insitutions of citing authors).
    '''
    # Fetch metadata for all publications.
    if num_processes > 1 and isinstance(num_processes, int):
        with Pool(processes=num_processes) as pool:
            all_publications = list(tqdm(pool.imap(__fill_publication_metadata, publications),
                                        desc='Filling metadata for all publications',
                                        total=len(publications)))
    else:
        all_publications = []
        for pub in tqdm(publications, desc='Filling metadata for all publications', total=len(publications)):
            all_publications.append(__fill_publication_metadata(pub))

    # Convert all publications to Google Scholar publication IDs.
    # This is fast and no parallel processing is needed.
    all_publication_ids = []
    for pub in all_publications:
        if 'cites_id' in pub:
            for cites_id in pub['cites_id']:
                all_publication_ids.append(cites_id)

    # Find all citing authors from all publications.
    if num_processes > 1 and isinstance(num_processes, int):
        with Pool(processes=num_processes) as pool:
            all_citing_authors_nested = list(tqdm(pool.imap(__citing_author_ids_from_publication, all_publication_ids),
                                                 desc='Finding all citing authors from cited publications',
                                                 total=len(all_publication_ids)))
    else:
        all_citing_authors_nested = []
        for pub in tqdm(all_publication_ids, desc='Finding all citing authors from cited publications', total=len(all_publication_ids)):
            all_citing_authors_nested.append(__citing_author_ids_from_publication(pub))
    all_citing_authors = list(itertools.chain(*all_citing_authors_nested))

    # Find all citing insitutions from all citing authors.
    if num_processes > 1 and isinstance(num_processes, int):
        with Pool(processes=num_processes) as pool:
            author_institution_tuple_list = list(tqdm(pool.imap(__institutions_from_authors, all_citing_authors),
                                                    desc='Finding all citing institutions from citing authors',
                                                    total=len(all_citing_authors)))
    else:
        author_institution_tuple_list = []
        for author in tqdm(all_citing_authors, desc='Finding all citing institutions from citing authors', total=len(all_citing_authors)):
            author_institution_tuple_list.append(__institutions_from_authors(author))

    return author_institution_tuple_list

def clean_institution_names(author_institution_tuple_list: List[Tuple[str]]) -> List[Tuple[str]]:
    '''
    Step 3. Clean up the name of institutions from the author's self-entered Google Scholar affiliation.
    NOTE: This logic is very naive. Please send an issue or pull request if you have any idea how to improve it.
    Currently we will not consider any paid service or tools that pose extra burden on the users, such as GPT API.
    '''
    cleaned_author_institution_tuple_list = []
    for author_name, institution_string in author_institution_tuple_list:
        # Use a regular expression to split the string by ',', ';', or 'and'.
        substring_list = [part.strip() for part in re.split(r'[;,]|\band\b', institution_string)]
        for substring in substring_list:
            # Use a regular expression to remove anything before 'at', or '@'.
            cleaned_institution = re.sub(r'.*?\bat\b|.*?@', '', substring, flags=re.IGNORECASE).strip()
            # Use a regular expression to filter out strings that represent
            # a person's identity rather than affiliation.
            is_common_identity_string = re.search(
                re.compile(
                    r'\b(director|manager|chair|engineer|programmer|scientist|professor|lecturer|phd|student|ph\.d|department of)\b',
                    re.IGNORECASE),
                substring)
            if not is_common_identity_string:
                cleaned_author_institution_tuple_list.append((author_name, cleaned_institution))
    return cleaned_author_institution_tuple_list

def institution_text_to_geocode(author_institution_tuple_list: List[Tuple[str]], max_attempts: int = 3) -> List[Tuple[str]]:
    '''
    Step 4: Convert institutions in plain text to Geocode.
    '''
    coordinates = []
    # NOTE: According to the Nomatim Usage Policy (https://operations.osmfoundation.org/policies/nominatim/),
    # we are explicitly asked not to submit bulk requests on multiple threads.
    # Therefore, we will keep it to a loop instead of multiprocessing.
    geolocator = Nominatim(user_agent='citation_mapper')
    for author_institution_tuple in tqdm(author_institution_tuple_list,
                                         desc='Finding all geographic coordinates from citing institutions',
                                         total=len(author_institution_tuple_list)):
        for _ in range(max_attempts):
            try:
                author_name, institution_name = author_institution_tuple
                geo_location = geolocator.geocode(institution_name)
                if geo_location:
                    coordinates.append((geo_location.latitude, geo_location.longitude, author_name, institution_name))
            except:
                continue
    coordinates = [item for item in coordinates if item is not None]  # Filter out empty coordinates.
    return coordinates

def create_map(coordinates: List[Tuple[str]], pin_colorful: bool = True):
    '''
    Step 5: Create the Citation World Map.
    '''
    citation_map = folium.Map(location=[20, 0], zoom_start=2)
    if pin_colorful:
        colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred',
                  'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue',
                  'darkpurple', 'pink', 'lightblue', 'lightgreen',
                  'gray', 'black', 'lightgray']
        for lat, lon, author_name, location in coordinates:
            color = random.choice(colors)
            folium.Marker([lat, lon], popup='%s (%s)' % (location, author_name), icon=folium.Icon(color=color)).add_to(citation_map)
    else:
        for lat, lon, author_name, location in coordinates:
            folium.Marker([lat, lon], popup='%s (%s)' % (location, author_name)).add_to(citation_map)
    return citation_map

def __fill_publication_metadata(pub):
    time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.
    return scholarly.fill(pub)

def __citing_author_ids_from_publication(cites_id: str):
    citing_paper_search_url = 'https://scholar.google.com/scholar?hl=en&cites=' + cites_id
    citing_author_ids = get_author_ids(citing_paper_search_url)
    return citing_author_ids

def __institutions_from_authors(author_id: str):
    time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.
    citing_author = scholarly.search_author_id(author_id)
    if 'affiliation' in citing_author:
        return (citing_author['name'], citing_author['affiliation'])
    return []


def generate_citation_map(scholar_id: str,
                          output_path: str = 'citation_map.html',
                          num_processes: int = 16,
                          use_proxy: bool = False,
                          pin_colorful: bool = True,
                          print_citing_institutions: bool = True):
    '''
    Google Scholar Citation World Map.

    Parameters
    ----
    scholar_id: str
        Your Google Scholar ID.
    output_path: str
        (default is 'citation_map.html')
        The path to the output HTML file.
    num_processes: int
        (default is 16)
        Number of processes for parallel processing.
    use_proxy: bool
        (default is False)
        If true, we will use a scholarly proxy.
        It is necessary for some environments to avoid blocks, but it usually makes things slower.
    pin_colorful: bool
        (default is True)
        If true, the location pins will have a variety of colors.
        Otherwise, it will only have one color.
    print_citing_institutions: bool
        (default is True)
        If true, print the list of citing institutions (affiliations of citing authors).
    '''

    if use_proxy:
        pg = ProxyGenerator()
        pg.FreeProxies()
        scholarly.use_proxy(pg)
        print('Using proxy.')

    author_profile = fetch_google_scholar_profile(scholar_id)
    print('\nAuthor profile found, with %d publications.\n' % len(author_profile['publications']))

    author_institution_tuple_list = find_all_citing_institutions(author_profile['publications'],
                                                                 num_processes=num_processes)
    print('\nA total of %d citing institutions recorded.\n' % len(author_institution_tuple_list))

    # Take unique tuples.
    author_institution_tuple_list = list(set(author_institution_tuple_list))

    if print_citing_institutions:
        print('\nList of all citing authors and institutions before cleaning:\n')
        for item in sorted((author_institution_tuple_list)):
            print(item)

    cleaned_author_institution_tuple_list = clean_institution_names(author_institution_tuple_list)

    # Take unique tuples.
    cleaned_author_institution_tuple_list = list(set(cleaned_author_institution_tuple_list))

    if print_citing_institutions:
        print('\nList of all citing authors and institutions after cleaning:\n')
        for item in sorted(cleaned_author_institution_tuple_list):
            print(item)

    coordinates = institution_text_to_geocode(author_institution_tuple_list + cleaned_author_institution_tuple_list)
    print('\nConverted the institutions to %d Geocodes.' % len(coordinates))

    citation_map = create_map(coordinates, pin_colorful=pin_colorful)
    citation_map.save(output_path)
    print('\nMap created and saved at %s.' % output_path)
    return


if __name__ == '__main__':
    # Replace this with your Google Scholar ID.
    scholar_id = '3rDjnykAAAAJ'
    generate_citation_map(scholar_id, output_path='citation_map.html',
                          num_processes=16, use_proxy=False, pin_colorful=True, print_citing_institutions=True)
