import folium
import itertools
import pandas as pd
import pycountry
import re
import random
import time

from geopy.geocoders import Nominatim
from multiprocessing import Pool
from scholarly import scholarly, ProxyGenerator
from tqdm import tqdm
from typing import List, Tuple

from .scholarly_support import get_citing_author_ids_and_citing_papers


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
                                         desc='Filling metadata for your %d publications' % len(publications),
                                         total=len(publications)))
    else:
        all_publications = []
        for pub in tqdm(publications,
                        desc='Filling metadata for your %d publications' % len(publications),
                        total=len(publications)):
            all_publications.append(__fill_publication_metadata(pub))

    # Convert all publications to Google Scholar publication IDs and paper titles.
    # This is fast and no parallel processing is needed.
    all_publication_info = []
    for pub in all_publications:
        if 'cites_id' in pub:
            for cites_id in pub['cites_id']:
                pub_title = pub['bib']['title']
                all_publication_info.append((cites_id, pub_title))

    # Find all citing authors from all publications.
    if num_processes > 1 and isinstance(num_processes, int):
        with Pool(processes=num_processes) as pool:
            all_citing_author_paper_info_nested = list(tqdm(pool.imap(__citing_authors_and_papers_from_publication, all_publication_info),
                                                            desc='Finding citing authors and papers on your %d publications' % len(all_publication_info),
                                                            total=len(all_publication_info)))
    else:
        all_citing_author_paper_info_nested = []
        for pub in tqdm(all_publication_info,
                        desc='Finding citing authors and papers on your %d publications' % len(all_publication_info),
                        total=len(all_publication_info)):
            all_citing_author_paper_info_nested.append(__citing_authors_and_papers_from_publication(pub))
    all_citing_author_paper_info_list = list(itertools.chain(*all_citing_author_paper_info_nested))

    # Find all citing insitutions from all citing authors.
    if num_processes > 1 and isinstance(num_processes, int):
        with Pool(processes=num_processes) as pool:
            author_paper_institution_tuple_list = list(tqdm(pool.imap(__institutions_from_authors, all_citing_author_paper_info_list),
                                                            desc='Finding citing institutions from %d citing authors' % len(all_citing_author_paper_info_list),
                                                            total=len(all_citing_author_paper_info_list)))
    else:
        author_paper_institution_tuple_list = []
        for author_and_paper in tqdm(all_citing_author_paper_info_list,
                                     desc='Finding citing institutions from %d citing authors' % len(all_citing_author_paper_info_list),
                                     total=len(all_citing_author_paper_info_list)):
            author_paper_institution_tuple_list.append(__institutions_from_authors(author_and_paper))

    return author_paper_institution_tuple_list

def clean_institution_names(author_paper_institution_tuple_list: List[Tuple[str]]) -> List[Tuple[str]]:
    '''
    Step 3. Clean up the names of institutions from the authors' affiliations on their Google Scholar profiles.
    NOTE: This logic is very naive. Please send an issue or pull request if you have any idea how to improve it.
    Currently we will not consider any paid service or tools that pose extra burden on the users, such as GPT API.
    '''
    cleaned_author_paper_institution_tuple_list = []
    for author_name, citing_paper_title, cited_paper_title, institution_string in author_paper_institution_tuple_list:
        # Use a regular expression to split the string by ';' or 'and'.
        substring_list = [part.strip() for part in re.split(r'[;]|\band\b', institution_string)]
        # Further split the substrings by ',' if the latter component is not a country.
        substring_list = __country_aware_comma_split(substring_list)

        for substring in substring_list:
            # Use a regular expression to remove anything before 'at', or '@'.
            cleaned_institution = re.sub(r'.*?\bat\b|.*?@', '', substring, flags=re.IGNORECASE).strip()
            # Use a regular expression to filter out strings that represent
            # a person's identity rather than affiliation.
            is_common_identity_string = re.search(
                re.compile(
                    r'\b(director|manager|chair|engineer|programmer|scientist|professor|lecturer|phd|ph\.d|postdoc|doctor|student|department of)\b',
                    re.IGNORECASE),
                cleaned_institution)
            if not is_common_identity_string:
                cleaned_author_paper_institution_tuple_list.append((author_name, citing_paper_title, cited_paper_title, cleaned_institution))
    return cleaned_author_paper_institution_tuple_list

def institution_text_to_geocode(author_paper_institution_tuple_list: List[Tuple[str]], max_attempts: int = 3) -> List[Tuple[str]]:
    '''
    Step 4: Convert institutions in plain text to Geocode.
    '''
    coordinates = []
    # NOTE: According to the Nomatim Usage Policy (https://operations.osmfoundation.org/policies/nominatim/),
    # we are explicitly asked not to submit bulk requests on multiple threads.
    # Therefore, we will keep it to a loop instead of multiprocessing.
    geolocator = Nominatim(user_agent='citation_mapper')

    # Find unique institutions and record their corresponding entries.
    institution_map = {}
    for entry_idx, (_, _, _, institution_name) in enumerate(author_paper_institution_tuple_list):
        if institution_name not in institution_map.keys():
            institution_map[institution_name] = [entry_idx]
        else:
            institution_map[institution_name].append(entry_idx)

    for institution_name in tqdm(institution_map,
                                 desc='Finding geographic coordinates from %d unique citing institutions in %d entries' % (
                                     len(institution_map), len(author_paper_institution_tuple_list)),
                                 total=len(institution_map)):
        for _ in range(max_attempts):
            try:
                geo_location = geolocator.geocode(institution_name)
                if geo_location:
                    # Get the full location metadata that includes county, city, state, country, etc.
                    location_metadata = geolocator.reverse(str(geo_location.latitude) + ',' + str(geo_location.longitude), language='en')
                    address = location_metadata.raw['address']
                    county, city, state, country = None, None, None, None
                    if 'county' in address:
                        county = address['county']
                    if 'city' in address:
                        city = address['city']
                    if 'state' in address:
                        state = address['state']
                    if 'country' in address:
                        country = address['country']

                    corresponding_entries = institution_map[institution_name]
                    for entry_idx in corresponding_entries:
                        author_name, citing_paper_title, cited_paper_title, institution_name = author_paper_institution_tuple_list[entry_idx]
                        coordinates.append((author_name, citing_paper_title, cited_paper_title, institution_name,
                                            geo_location.latitude, geo_location.longitude,
                                            county, city, state, country))
            except:
                continue
    coordinates = [item for item in coordinates if item is not None]  # Filter out empty coordinates.
    return coordinates

def create_map(coordinates_and_info: List[Tuple[str]], pin_colorful: bool = True):
    '''
    Step 5: Create the Citation World Map.
    '''
    citation_map = folium.Map(location=[20, 0], zoom_start=2)
    if pin_colorful:
        colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred',
                  'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue',
                  'darkpurple', 'pink', 'lightblue', 'lightgreen',
                  'gray', 'black', 'lightgray']
        for author_name, _, _, institution_name, lat, lon, _, _, _, _ in coordinates_and_info:
            color = random.choice(colors)
            folium.Marker([lat, lon], popup='%s (%s)' % (institution_name, author_name),
                          icon=folium.Icon(color=color)).add_to(citation_map)
    else:
        for author_name, _, _, institution_name, lat, lon, _, _, _, _ in coordinates_and_info:
            folium.Marker([lat, lon], popup='%s (%s)' % (institution_name, author_name)).add_to(citation_map)
    return citation_map

def export_csv(coordinates_and_info: List[Tuple[str]], csv_output_path: str) -> None:
    '''
    Step 6: Export csv file recording citing authors.
    '''

    citation_df = pd.DataFrame(coordinates_and_info,
                               columns=['citing author name', 'citing paper title', 'cited paper title',
                                        'affiliated institution', 'latitude', 'longitude',
                                        'county', 'city', 'state', 'country'])

    citation_df.to_csv(csv_output_path)
    return

def __fill_publication_metadata(pub):
    time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.
    return scholarly.fill(pub)

def __citing_authors_and_papers_from_publication(cites_id_and_cited_paper: Tuple[str, str]):
    cites_id, cited_paper_title = cites_id_and_cited_paper
    citing_paper_search_url = 'https://scholar.google.com/scholar?hl=en&cites=' + cites_id
    citing_authors_and_citing_papers = get_citing_author_ids_and_citing_papers(citing_paper_search_url)
    citing_author_paper_info = []
    for citing_author_id, citing_paper_title in citing_authors_and_citing_papers:
        citing_author_paper_info.append((citing_author_id, citing_paper_title, cited_paper_title))
    return citing_author_paper_info

def __institutions_from_authors(citing_author_paper_info: str):
    citing_author_id, citing_paper_title, cited_paper_title = citing_author_paper_info
    time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.
    citing_author = scholarly.search_author_id(citing_author_id)
    if 'affiliation' in citing_author:
        return (citing_author['name'], citing_paper_title, cited_paper_title, citing_author['affiliation'])
    return []

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

def generate_citation_map(scholar_id: str,
                          output_path: str = 'citation_map.html',
                          csv_output_path: str = 'citation_info.csv',
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
    csv_output_path: str
        (default is 'citation_info.csv')
        The path to the output csv file.
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

    author_paper_institution_tuple_list = find_all_citing_institutions(author_profile['publications'],
                                                                       num_processes=num_processes)
    print('\nA total of %d citing institutions recorded.\n' % len(author_paper_institution_tuple_list))

    # Take unique tuples.
    author_paper_institution_tuple_list = list(set(author_paper_institution_tuple_list))

    if print_citing_institutions:
        print('\nList of all citing authors and institutions before cleaning:\n')
        for author, _, _, institution in sorted(author_paper_institution_tuple_list):
            print('Author: %s, Institution: %s.' % (author, institution))

    cleaned_author_paper_institution_tuple_list = clean_institution_names(author_paper_institution_tuple_list)

    # Take unique tuples.
    cleaned_author_paper_institution_tuple_list = list(set(cleaned_author_paper_institution_tuple_list))

    if print_citing_institutions:
        print('\nList of all citing authors and institutions after cleaning:\n')
        for author, _, _, institution in sorted(cleaned_author_paper_institution_tuple_list):
            print('Author: %s, Institution: %s.' % (author, institution))

    coordinates_and_info = institution_text_to_geocode(author_paper_institution_tuple_list + cleaned_author_paper_institution_tuple_list)
    # Take unique tuples.
    coordinates_and_info = list(set(coordinates_and_info))
    print('\nConverted the institutions to %d Geocodes.' % len(coordinates_and_info))

    citation_map = create_map(coordinates_and_info, pin_colorful=pin_colorful)
    citation_map.save(output_path)
    print('\nMap created and saved at %s.\n' % output_path)

    export_csv(coordinates_and_info, csv_output_path)
    print('\nCitation information exported to %s.' % csv_output_path)
    return


if __name__ == '__main__':
    # Replace this with your Google Scholar ID.
    scholar_id = '3rDjnykAAAAJ'
    generate_citation_map(scholar_id, output_path='citation_map.html', csv_output_path='citation_info.csv',
                          num_processes=16, use_proxy=False, pin_colorful=True, print_citing_institutions=True)
