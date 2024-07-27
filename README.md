# Google Scholar Citation World Map

[Chen Liu](https://www.chenliu1996.com/), CS PhD Candidate at Yale University.

Research areas: Machine Learning, Spatial-Temporal Modeling, Medical Vision, AI4Science.

## Purpose
This is a simple Python tool to generate an HTML citation world map from your Google Scholar ID.

It is easy to install (`pip install citation-map`, available on [PyPI](https://pypi.org/project/citation-map/)) and easy to use (see the [Usage](https://github.com/ChenLiu-1996/CitationMap?tab=readme-ov-file#usage) section).

## Expected Outcome
You will be given an HTML file as the output of the script.

If you open it on a browser, you will see your own version of the following citation world map.

<img src = "assets/citation_world_map.png" width=800>

## Warning
1. Runtime concerns.
    - This script is a bit slow. On my personal computer, it takes half a minute to process each citation. If you have thousands of citations, it may or may not be a good idea to use this script.
    - I tried to use multiprocessing, but sadly the excessive visits get me blocked by Google Scholar.
    - I am a researcher and am not very good at software engineering. If you have any idea how to improve the runtime, you are very welcome to submit a pull request.

## Usage
1. Install the package.
    ```
    pip install citation-map
    ```

2. Find your Google Scholar ID.

    - Open your Google Scholar profile. The URL should take the form of `https://scholar.google.com/citations?user=GOOGLE_SCHOLAR_ID`. In this case, your Google Scholar ID is just the string `GOOGLE_SCHOLAR_ID`.
    - Please kindly ignore configuration strings such as `&hl=en` (host language is English) or `&sortby=pubdate` (sort the works by date of publication).

3. In an empty Python script (for example, [the demo script](https://github.com/ChenLiu-1996/CitationMap/blob/main/demo/demo.py)), run the following.
    ```
    from citation_map import generate_citation_map

    # This is my Google Scholar ID. Replace this with your ID.
    scholar_id = '3rDjnykAAAAJ'
    generate_citation_map(scholar_id)
    ```

    You can take a look at the input arguments (listed below) of the function `generate_citation_map` in case you need those functionalities.

    ```
    Parameters
    ----
    scholar_id: str
        Your Google Scholar ID.
    output_path: str
        (default is 'citation_map.html')
        The path to the output HTML file.
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
    ```

## Dependencies
Dependencies (`scholarly`, `geopy`, `folium`, `tqdm`) are already taken care of when you install via pip.

## Acknowledgements
This script was written under the assistance of ChatGPT-4o, but of course after intense debugging.
