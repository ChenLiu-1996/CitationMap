from setuptools import setup

with open('README.md') as f:
    long_description = f.read()

setup(
    name='citation-map',
    version='4.6',
    license='CC BY-NC-SA',
    author='Chen Liu',
    author_email='chen.liu.cl2482@yale.edu',
    packages={'citation_map'},
    # package_dir={'': ''},
    description='A simple tool to generate your Google Scholar citation world map.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/ChenLiu-1996/CitationMap',
    keywords='citation map, citation world map, google scholar',
    install_requires=['scholarly', 'geopy', 'folium', 'tqdm', 'requests', 'bs4', 'pycountry', 'pandas'],
    classifiers=[
    'Development Status :: 3 - Alpha',      # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
    'Intended Audience :: Developers',      # Define that your audience are developers
    'License :: Other/Proprietary License',   # Again, pick a license
    'Programming Language :: Python :: 3',      #Specify which pyhton versions that you want to support
    ],
)