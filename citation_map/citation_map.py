from scholarly import scholarly, ProxyGenerator
from geopy.geocoders import Nominatim
import folium
from tqdm import tqdm
import random


def __fetch_google_scholar_profile(scholar_id):
    '''
    Step 1: Fetch Google Scholar Profile using Scholar ID.
    '''
    author = scholarly.search_author_id(scholar_id)
    author = scholarly.fill(author, sections=['publications'])
    return author

def __parse_profile(author):
    '''
    Step 2: Parse the Profile and find citing author affiliations.

    NOTE: Usually this is the most time-consuming part of the code.
    I tried to parallel process this, which indeed makes it faster,
    but unfortunately the frequent visiting makes Google Scholar block me. T_T
    You are very welcome to submit a pull request if you can help optimize this code.
    '''
    citing_institutions = []
    for pub_idx, pub in enumerate(tqdm(author['publications'], desc='publication iterator')):
        pub = scholarly.fill(pub)
        if 'citedby_url' in pub:
            citing_paper_obj = scholarly.citedby(pub)
            citing_paper_list = [item for item in citing_paper_obj]
            for citing_paper in tqdm(citing_paper_list,
                                     desc='citation iterator (for publication #%d/%d)' % (
                                        pub_idx + 1, len(author['publications'])
                                     )):
                if 'author_id' in citing_paper:
                    author_id_list = citing_paper['author_id']
                    author_id_list = [item for item in author_id_list if item]  # Filter out empty author ids.

                    for author_id in author_id_list:
                        citing_author = scholarly.search_author_id(author_id)
                        citing_author = scholarly.fill(citing_author)
                        if 'affiliation' in citing_author:
                            citing_institutions.append(citing_author['affiliation'])
    return citing_institutions

def __geocode_locations(institutions):
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

def __create_map(coordinates, pin_colorful: bool = True):
    '''
    Step 4: Create the Map.
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

def generate_citation_map(scholar_id: str,
                          output_path: str = 'citation_map.html',
                          use_proxy: bool = False,
                          pin_colorful: bool = True,
                          print_citing_institutions: bool = True):
    '''
    Google Scholar Citation World Map.

    Parameters
    ----
    scholar_id: str
        Your Google Scholar ID.
    use_proxy: bool
        (default is False)
        If true, we will use a scholarly proxy.
        It is necessary for some environments to avoid blocks, but it usually makes things slower.
    pin_colorful: bool
        (default is True)
        If true, the location pins will have a variety of colors.
        Otherwise, it will only have one color.
    output_path: str
        (default is 'citation_map.html')
        The path to the output HTML file.
    print_citing_institutions: bool
        (default is True)
        If true, print the list of citing institutions (affiliations of citing authors).
    '''

    if use_proxy:
        pg = ProxyGenerator()
        pg.FreeProxies()
        scholarly.use_proxy(pg)
        print('Using proxy.')

    author = __fetch_google_scholar_profile(scholar_id)
    print('Author profile found, with %d publications.' % len(author['publications']))

    institutions = __parse_profile(author)
    print('A total of %d citation locations recorded.' % len(institutions))

    coordinates = __geocode_locations(institutions)
    print('Converted the locations to Geocodes.')

    citation_map = __create_map(coordinates, pin_colorful=pin_colorful)
    citation_map.save(output_path)
    print('Map created and saved as citation_map.html.')

    if print_citing_institutions:
        print('\n\nList of all institutions:')
        for institution in sorted(institutions):
            print(institution)
    return


if __name__ == '__main__':
    # Replace this with your Google Scholar ID.
    scholar_id = '3rDjnykAAAAJ'
    generate_citation_map(scholar_id, output_path='citation_map.html',
                          use_proxy=False, pin_colorful=True, print_citing_institutions=True)
