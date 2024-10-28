# Google Scholar Citation World Map

[![TechRxiv](https://img.shields.io/badge/TechRxiv-darkviolet)](https://www.techrxiv.org/users/809001/articles/1213717-citationmap-a-python-tool-to-identify-and-visualize-your-google-scholar-citations-around-the-world)
[![OpenReview](https://img.shields.io/badge/OpenReview-firebrick)](https://openreview.net/pdf?id=BqJgCgl1IA)
[![Latest PyPI version](https://img.shields.io/pypi/v/citation-map.svg)](https://pypi.org/project/citation-map/)
[![PyPI download month](https://img.shields.io/pypi/dm/citation-map.svg)](https://pypistats.org/packages/citation-map)
[![PyPI download day](https://img.shields.io/pypi/dd/citation-map.svg)](https://pypistats.org/packages/citation-map)
[![CC BY-NC-SA 4.0][cc-by-nc-sa-shield]][cc-by-nc-sa]
[![CC BY-NC-SA 4.0][cc-by-nc-sa-image]][cc-by-nc-sa]

[cc-by-nc-sa]: http://creativecommons.org/licenses/by-nc-sa/4.0/
[cc-by-nc-sa-image]: https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png
[cc-by-nc-sa-shield]: https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg

[Chen Liu](https://chenliu-1996.github.io/), CS PhD Candidate at Yale University.

Research areas: Machine Learning, Spatial-Temporal Modeling, Medical Vision, AI4Science.


## News
**[Asking for advice]**
1. This is my first time dealing with webscraping/crawling. Users have reported stability issues, and I suspect the major problems are (1) being caught by CAPTCHA or robot check, and (2) being flagged for blacklist by Google Scholar. If you are experienced in these areas and have good advice, I would highly appreciate a **GitHub issue or a pull request**.

[Aug 2, 2024] Version 4.0 released >>> Logic update. A new input argument `affiliation_conservative`. If set to True, we will use **a very conservative approach to identify affiliations** which leads to **much higher precision and lower recall**. Many thanks to [Zhijian Liu](https://github.com/zhijian-liu) for the [helpful discussion](https://github.com/ChenLiu-1996/CitationMap/issues/8).

[Jul 28, 2024] Version 3.10 released >>> Logic update. Tested on a professor's profile **with 10,000 citations**!

[Jul 27, 2024] Version 2.0 released >>> 10x speedup with multiprocessing (1 hour to 5 minutes for my profile).

[Jul 26, 2024] Version 1.0 released >>> First working version for my profile with 100 citations.

## Purpose
This is a simple Python tool to generate an HTML citation world map from your Google Scholar ID.

It is easy to install (`pip install citation-map`, available on [PyPI](https://pypi.org/project/citation-map/)) and easy to use (see the [User Guide](https://github.com/ChenLiu-1996/CitationMap?tab=readme-ov-file#user-guide)).

**You don't need to fork this repo unless you want to make custom changes.**

## Expected Outcome
You will be given an **HTML file** as the output of the script.

If you open it on a browser, you will see your own version of the following citation world map.

<img src = "assets/citation_world_map.png" width=800>

Besides, there will be a **CSV file** recording citation information (citing author, citing paper, cited paper, affiliation, detailed location).

**Disclaimer:** It is reasonable for this tool to make some minor mistakes: missing a few citing authors, dropping a couple of pins in wrong locations, etc. If you care a lot about ensuring all citing authors' affiliations are included and accurately marked, you could try manually annotating on [Google My Maps](https://www.google.com/maps/d/) instead. This tool is meant to help people who cannot tolerate this painful process, especailly when they have a decent number of citations.

**NOTE:** **Now you can trade off between affiliation precision and recall** with the `affiliation_conservative` option. If set to True, we will use the Google Scholar verified official organization name from the citing authors. This is a very conservative approach, since (1) the author needs to self-report it in the affiliation panel, (2) the author needs to verify with the matching email address, and (3) the organization needs to be recorded by Google Scholar. For example, Meta (the company) is not in the list. Many thanks to [Zhijian Liu](https://github.com/zhijian-liu) for the [helpful discussion](https://github.com/ChenLiu-1996/CitationMap/issues/8).

## Citation
BibTeX
```
@article{citationmap,
  title={CitationMap: A Python Tool to Identify and Visualize Your Google Scholar Citations Around the World},
  author={Liu, Chen},
  journal={Authorea Preprints},
  year={2024},
  publisher={Authorea}
}
```
MLA
```
Liu, Chen. "CitationMap: A Python Tool to Identify and Visualize Your Google Scholar Citations Around the World." Authorea Preprints (2024).
```
APA
```
Liu, C. (2024). CitationMap: A Python Tool to Identify and Visualize Your Google Scholar Citations Around the World. Authorea Preprints.
```
Chicago
```
Liu, Chen. "CitationMap: A Python Tool to Identify and Visualize Your Google Scholar Citations Around the World." Authorea Preprints (2024).
```

## User Guide
0. If you are new to Python, you probably want to start with a distribution of Python that also helps with environment management (such as [anaconda](https://www.anaconda.com/)). Once you have set up your environment (for example, when you reach the stage of `conda activate env39` in [this tutorial](https://www.youtube.com/watch?v=MUZtVEDKXsk&t=242s)), you can move on to the next step.
1. Install this tool by running the following line in your conda-accessible command line.
    ```
    pip install citation-map --upgrade
    ```

2. Find your Google Scholar ID.

    - Open your Google Scholar profile. The URL should take the form of `https://scholar.google.com/citations?user=GOOGLE_SCHOLAR_ID`. In this case, your Google Scholar ID is just the string `GOOGLE_SCHOLAR_ID`.
    - Please kindly ignore configuration strings such as `&hl=en` (host language is English) or `&sortby=pubdate` (sort the works by date of publication).
    - **NOTE**: If you have publications/patents that you **_manually added into the Google Scholar page_**, you might want to temporarily delete them while you run this tool. They might cause errors due to incompatibility.

3. In an empty Python script, run the following.

    - **NOTE 1**: Please **DO NOT** name your script `citation_map.py` which would cause circular import as this package itself shares the same name. Call it something else: e.g., `run_citation_map.py`, `run.py`, etc. See [Issue #2](https://github.com/ChenLiu-1996/CitationMap/issues/2).
    - **NOTE 2**: Protecting with `if __name__ == '__main__'` seems necessary to avoid multiprocessing problems, and it is a good practice anyways.
    ```
    from citation_map import generate_citation_map

    if __name__ == '__main__':
        # This is my Google Scholar ID. Replace this with your ID.
        scholar_id = '3rDjnykAAAAJ'
        generate_citation_map(scholar_id)
    ```

    Note that in Version 4.0, we will cache the results before identifying affiliations. So if you want to rerun the same author from scratch, you need to delete the cache (default location is 'cache').

    More input arguments are shown in [the demo script](https://github.com/ChenLiu-1996/CitationMap/blob/main/demo/demo.py).

    You can take a look at the input arguments (listed below) of the function `generate_citation_map` in case you need those functionalities.

    ```
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
    print_citing_affiliations: bool
        (default is True)
        If true, print the list of citing affiliations (affiliations of citing authors).
    ```

## Limitations

1. This tool is purely based on Google Scholar. As a result, you are expected to have underestimations due to reasons such as:
    - Your Google Scholar profile is not up-to-date.
    - Some papers citing you are not indexed by Google Scholar.
    - Some authors citing you do not have Google Scholar profiles.
    - Some authors citing you do not report their affiliations.
2. Webscraping is performed, and CAPTCHA or robot check can often get us, especially if we crawl frequently. This is more often seen in highly cited users. Unless you are blocked by Google Scholar, at worst you will end up with missing several citing authors, which is not likely a huge deal for highly cited users anyways.
3. Affiliation identification and geolocating issues. This is a joint effect between affiliation identification and geolocating. The number of citing affiliations will be:
    - Underestimated if some affiliations are not found by `geopy.geocoders`.
    - Underestimated if we experience communication errors with `geopy.geocoders`.
    - (Aggressive approach only) Overestimated if non-affiliation phrases are incorrectly identified as locations by `geopy.geocoders`.
    - (Conservative approach only) Underestimated if the citer did not verify with an email address under a matching affiliation domain.
    - (Conservative approach only) Underestimated because all non-primary (with verified email address) affiliations are ignored.

    **Please raise an issue or submit a pull request if you have some good idea to better process the affiliation string. Note that currently I am not considering any paid service or tools that pose extra burden on the users, such as GPT API.**


## Debug

1. `MaxTriesExceededException` or `Exception: Failed to fetch the Google Scholar page` or (`[WARNING!] Blocked by CAPTCHA or robot check` for all entries).

    - From my experience, these are good indicators that your IP address is blocked by Google Scholar due to excessive crawling (using the `scholarly` package).
    - One hot fix I found was to hop on a University VPN and run again. I typically experience this error after running the tool twice, and I need to disconnect and reconnect my VPN to "unblock" myself.
    - In case this does not help, you can try to change IP adress and reduce the number of processes (e.g., setting `num_processes=1`).
    - If you get `[WARNING!] Blocked by CAPTCHA or robot check` no more than several times, it's not a big deal especially if you have many citing authors.

2. `An attempt has been made to start a new process before the current process has finished its bootstrapping phase.`

    - I believe this is because you did not protect your main function with `if __name__ == '__main__'`. You can take a look at the recommended script again.
    - If this still does not help, you might want to write your script slightly differently. Credit to [dk-liang](https://github.com/dk-liang) in [Issue #4](https://github.com/ChenLiu-1996/CitationMap/issues/4#issuecomment-2257572672).
      ```
      from citation_map import generate_citation_map

      def main():
          # This is my Google Scholar ID. Replace this with your ID.
          scholar_id = '3rDjnykAAAAJ'
          generate_citation_map(scholar_id)

      if __name__ == '__main__':
          import multiprocessing
          multiprocessing.freeze_support()
          main()
      ```

## Changelog
<details>
<summary>Version 4.0 (Aug 2, 2024)</summary>
<br>

1. **Now you can trade off between precision and recall as we identify the affiliations.**
2. Added caching before identifying the affiliations, since users might want to try both the conservative and aggressive approaches.
3. Slight optimization in the affiliation to geocode stage by adding early breaking if successful.

</details>


<details>
<summary>Version 3.11 (Jul 28, 2024)</summary>
<br>

**Additional output CSV that records citation information.**
</details>

<details>
<summary>Version 3.10 (Jul 28, 2024)</summary>
<br>
In 3.10, I slightly improved the logic for affiliation extraction.

In 3.8, I removed multiprocessing for `geopy.geocoders` as per their official documentation. Also I cleaned up some unnecessary `scholarly` calls which further helps us not get blacklisted by Google Scholar.

In 3.7, I updated the logic for webscraping and avoided using `scholarly.citeby()` which is the biggest trigger of blacklisting from Google Scholar.

**Now we should be able to handle users with more citations than before. I tested on a profile with 1000 citations without running into any issue.**
</details>

<details>
<summary>Version 3.0 (Jul 27, 2024)</summary>
<br>
I realized a problem with how I used `geopy.geocoders`. A majority of the authors' affiliations include details that are irrelevant to the affiliation itself. Therefore, they are not successfully found in the system and hence are not converted to geographic coordinates on the world map.

For example, we would want the substring "Yale University" from the string "Assistant Professor at Yale University".

I applied a simple fix with some rule-based natural language processing. This helps us identify many missing citing locations.

**Please raise an issue or submit a pull request if you have some good idea to better process the affiliation string. Note that currently I am not considering any paid service or tools that pose extra burden on the users, such as GPT API.**
</details>

<details>
<summary>Version 2.0 (Jul 27, 2024)</summary>
<br>
I finally managed to **drastically speed up** the process using multiprocessing, in a way that avoids being blocked by Google Scholar.

On my personal computer, processing my profile with 100 citations took 1 hour with version 1.0 while it's now taking 5 minutes with version 2.0.

With that said, please be careful and do not run this tool frequently. I can easily get on Google Scholar's blacklist after a few runs.
</details>

<details>
<summary>Version 1.0 (Jul 26, 2024)</summary>
<br>
Very basic functionality.

This script is a bit slow. On my personal computer, it takes half a minute to process each citation. If you have thousands of citations, it may or may not be a good idea to use this script.

I tried to use multiprocessing, but unfortunately the excessive visits get me blocked by Google Scholar.
</details>

## Dependencies
Dependencies (`scholarly`, `geopy`, `folium`, `tqdm`, `requests`, `bs4`, `pycountry`, `pandas`) are already taken care of when you install via pip.

## Acknowledgements
This script was written under the assistance of ChatGPT-4o, but of course after intense debugging.
