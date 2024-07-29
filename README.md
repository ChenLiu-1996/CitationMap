# Google Scholar Citation World Map

[![Latest PyPI version](https://img.shields.io/pypi/v/citation-map.svg)](https://pypi.org/project/citation-map/)
[![PyPI download month](https://img.shields.io/pypi/dm/citation-map.svg)](https://pypi.python.org/pypi/citation-map/)
[![PyPI download day](https://img.shields.io/pypi/dd/citation-map.svg)](https://pypi.python.org/pypi/citation-map/)
[![made-with-python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/)


[Chen Liu](https://www.chenliu1996.com/), CS PhD Candidate at Yale University.

Research areas: Machine Learning, Spatial-Temporal Modeling, Medical Vision, AI4Science.

## Purpose
This is a simple Python tool to generate an HTML citation world map from your Google Scholar ID.

It is easy to install (`pip install citation-map`, available on [PyPI](https://pypi.org/project/citation-map/)) and easy to use (see the [Usage](https://github.com/ChenLiu-1996/CitationMap?tab=readme-ov-file#usage) section).

**You don't need to fork this repo unless you want to make custom changes.**

## Expected Outcome
You will be given an HTML file as the output of the script.

If you open it on a browser, you will see your own version of the following citation world map.

<img src = "assets/citation_world_map.png" width=800>


## Usage
1. Install the package.
    ```
    pip install citation-map --upgrade
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
    ```

## Limitations

1. This tool is purely based on Google Scholar. As a result, you are expected to have underestimations due to reasons such as:
    - Your Google Scholar profile is not up-to-date.
    - Some papers citing you are not indexed by Google Scholar.
    - Some authors citing you do not have Google Scholar profile.
    - Some authors citing you do not report their affiliations.
2. `geopy.geocoders` is used to convert the citing authors' affiliations to geographic coordinates. To facilitate the process, I used some simple rule-based natural language processing to clean up the affiliations. As a result, you are expected to have:
    - Underestimation if correct affiliations are not found by `geopy.geocoders`.
    - Underestimation if we experience communication error with `geopy.geocoders`.
    - Overestimation if non-affiliation terms are incorrectly identified as locations by `geopy.geocoders`.

    **Please raise an issue or submit a pull request if you have some good idea to better process the affiliation string. Note that currently I am not considering any paid service or tools that pose extra burden on the users, such as GPT API.**


## Debug
1. `MaxTriesExceededException` or `[WARNING!] Blocked by CAPTCHA or robot check`

    - From my experience, both are good indicators that your IP address is blocked by Google Scholar due to excessive crawling (using the `scholarly` package).
    - One hot fix I found was to hop on a University VPN and run again. I typically experience this error after running the tool twice, and I need to disconnect and reconnect my VPN to "unblock" myself.
    - In case this does not help, you can try to change IP adress and reduce the number of processes (e.g., setting `num_processes=1`).

## Changelog

<details>
<summary>Version 3.10</summary>
<br>
In 3.10, I slightly improved the logic for affiliation extraction.

In 3.8, I removed multiprocessing for `geopy.geocoders` as per their official documentation. Also I cleaned up some unnecessary `scholarly` calls which further helps us not get blacklisted by Google Scholar.

In 3.7, I updated the logic for webscraping and avoided using `scholarly.citeby()` which is the biggest trigger of blacklisting from Google Scholar.

**Now we should be able to handle users with more citations than before. I tested on a profile with 1000 citations without running into any issue.**
</details>

<details>
<summary>Version 3.0</summary>
<br>
I realized a problem with how I used `geopy.geocoders`. A majority of the authors' affiliations include details that are irrelevant to the affiliation itself. Therefore, they are not successfully found in the system and hence are not converted to geographic coordinates on the world map.

For example, we would want the substring "Yale University" from the string "Assistant Professor at Yale University".

I applied a simple fix with some rule-based natural language processing. This helps us identify many missing citing locations.

**Please raise an issue or submit a pull request if you have some good idea to better process the affiliation string. Note that currently I am not considering any paid service or tools that pose extra burden on the users, such as GPT API.**
</details>

<details>
<summary>Version 2.0</summary>
<br>
I finally managed to **drastically speed up** the process using multiprocessing, in a way that avoids being blocked by Google Scholar.

On my personal computer, processing my profile with 100 citations took 1 hour with version 1.0 while it's now taking 5 minutes with version 2.0.

With that said, please be careful and do not run this tool frequently. I can easily get on Google Scholar's blacklist after a few runs.
</details>

<details>
<summary>Version 1.0</summary>
<br>
Very basic functionality.

This script is a bit slow. On my personal computer, it takes half a minute to process each citation. If you have thousands of citations, it may or may not be a good idea to use this script.

I tried to use multiprocessing, but unfortunately the excessive visits get me blocked by Google Scholar.
</details>

## Dependencies
Dependencies (`scholarly`, `geopy`, `folium`, `tqdm`) are already taken care of when you install via pip.

## Acknowledgements
This script was written under the assistance of ChatGPT-4o, but of course after intense debugging.
