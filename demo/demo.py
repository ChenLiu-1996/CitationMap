from citation_map import generate_citation_map

if __name__ == '__main__':
    # This is my Google Scholar ID. Replace this with your ID.
    scholar_id = '3rDjnykAAAAJ'
    generate_citation_map(scholar_id, output_path='citation_map.html',
                          cache_folder='cache', parse_csv=False, affiliation_conservative=False, num_processes=16,
                          use_proxy=False, pin_colorful=True, print_citing_affiliations=True)
