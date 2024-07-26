# Google Scholar Citation World Map

Chen Liu, CS PhD Candidate at Yale University

## Purpose
This is a simple Python tool to generate a HTML citation world map from your Google Scholar ID.

## Usage
1. Install the package.
```
pip install citation-map
```

2. Find your Google Scholar ID.

    On your Google Scholar website, the string `YOUR_GOOGLE_SCHOLAR_ID` in the URL `https://scholar.google.com/citations?user=YOUR_GOOGLE_SCHOLAR_ID` be will be your Google Scholar ID. Ignore the configuration strings such as `&hl=en` or `&view_op=list_works&sortby=pubdate`.

3. In an empty Python script, run the following.
```
from citation_map import citation_map_from_google_scholar_id

# This is my ID. Replace this with your Google Scholar ID
scholar_id = "3rDjnykAAAAJ"
citation_map_from_google_scholar_id(scholar_id)
```

## NOTE
This script is a bit slow. On my end it takes half a minute to process each citation. If you have thousands of citations it may or may not be a good idea to use it.

## Dependencies
```
scholarly
geopy
folium
tqdm
```