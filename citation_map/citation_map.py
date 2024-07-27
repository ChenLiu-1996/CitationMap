import random
import time
import itertools
from scholarly import scholarly, ProxyGenerator
from geopy.geocoders import Nominatim
import folium
from tqdm import tqdm
from multiprocessing import Pool


def fetch_google_scholar_profile(scholar_id):
    '''
    Step 1: Fetch Google Scholar Profile using Scholar ID.
    '''
    author = scholarly.search_author_id(scholar_id)
    author = scholarly.fill(author, sections=['publications'])
    return author

def find_all_citing_institutions(publications, num_processes: int = 16):
    '''
    Step 2. Final all citing institutions (i.e., insitutions of citing authors).
    '''

    # Fetch metadata for all publications, in parallel.
    with Pool(processes=num_processes) as pool:
        all_publications = list(tqdm(pool.imap(__fill_publication_metadata, publications), desc='Filling metadata for all publications...', total=len(publications)))

    # Find all citing papers from all publications, in parallel.
    with Pool(processes=num_processes) as pool:
        all_citing_papers_nested = list(tqdm(pool.imap(__citing_papers_from_publication, all_publications), desc='Finding all citations...', total=len(all_publications)))
    all_citing_papers = list(itertools.chain(*all_citing_papers_nested))

    # Find all citing authors from all citing papers, in parallel.
    with Pool(processes=num_processes) as pool:
        all_citing_authors_nested = list(tqdm(pool.imap(__authors_from_papers, all_citing_papers), desc='Finding all citing authors...', total=len(all_citing_papers)))
    all_citing_authors = list(itertools.chain(*all_citing_authors_nested))

    # Find all citing insitutions from all citing authors, in parallel.
    with Pool(processes=num_processes) as pool:
        all_citing_insitutions = list(tqdm(pool.imap(__institutions_from_authors, all_citing_authors), desc='Finding all citing institutions...', total=len(all_citing_authors)))

    return sorted(all_citing_insitutions)

def text_to_geocode(institutions):
    '''
    Step 3: Convert institutions in plain text to Geocode.
    '''
    geolocator = Nominatim(user_agent='citation_mapper')
    coordinates = []
    for institution in institutions:
        try:
            geo_location = geolocator.geocode(institution)
            if geo_location:
                coordinates.append((geo_location.latitude, geo_location.longitude, institution))
        except Exception as e:
            print(f'Error geocoding institution {institution}: {e}')
    return coordinates

def create_map(coordinates, pin_colorful: bool = True):
    '''
    Step 4: Create the Citation World Map.
    '''
    citation_map = folium.Map(location=[20, 0], zoom_start=2)
    if pin_colorful:
        colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred',
                  'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue',
                  'darkpurple', 'pink', 'lightblue', 'lightgreen',
                  'gray', 'black', 'lightgray']
        for lat, lon, location in coordinates:
            color = random.choice(colors)
            folium.Marker([lat, lon], popup=location, icon=folium.Icon(color=color)).add_to(citation_map)
    else:
        for lat, lon, location in coordinates:
            folium.Marker([lat, lon], popup=location).add_to(citation_map)
    return citation_map

def __fill_publication_metadata(pub):
    time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.
    return scholarly.fill(pub)

def __citing_papers_from_publication(pub):
    if 'citedby_url' in pub:
        time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.
        citing_paper_obj = scholarly.citedby(pub)
        return [item for item in citing_paper_obj]
    return []

def __authors_from_papers(citing_paper):
    if 'author_id' in citing_paper:
        author_id_list = citing_paper['author_id']
        author_id_list = [item for item in author_id_list if item]  # Filter out empty author ids.
        return author_id_list
    return []

def __institutions_from_authors(author_id):
    time.sleep(random.uniform(1, 5))  # Random delay to reduce risk of being blocked.
    citing_author = scholarly.search_author_id(author_id)
    citing_author = scholarly.fill(citing_author)
    if 'affiliation' in citing_author:
        return citing_author['affiliation']
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
        Number of separate processes for parallel processing.
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

    institutions = find_all_citing_institutions(author_profile['publications'], num_processes=num_processes)
    print('\nA total of %d citing institutions recorded.' % len(institutions))

    coordinates = text_to_geocode(institutions)
    print('\nConverted the institutions to Geocodes.')

    citation_map = create_map(coordinates, pin_colorful=pin_colorful)
    citation_map.save(output_path)
    print('\nMap created and saved as citation_map.html.')

    if print_citing_institutions:
        print('\nList of all citing institutions:\n')
        for institution in institutions:
            print(institution)
    return


if __name__ == '__main__':
    # Replace this with your Google Scholar ID.
    scholar_id = '3rDjnykAAAAJ'
    generate_citation_map(scholar_id, output_path='citation_map.html',
                          num_processes=16, use_proxy=False, pin_colorful=True, print_citing_institutions=True)
