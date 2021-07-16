import json
import sys
import requests
import itertools
from pathlib import Path
from gzip_stream import GZIPCompressedStream
import structlog
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from os.path import basename

log = structlog.get_logger()


def download_file(url, local_path: Path):
    local_filename = url.split('/')[-1]
    # NOTE the stream=True parameter below
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with local_path.open('wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                # If you have chunk encoded response uncomment if
                # and set chunk_size parameter to None.
                #if chunk:
                f.write(chunk)
    return local_filename


def update_webdewey_cmd(config, options):
    print("Downloading...")
    download_file('https://data.ub.uio.no/dumps/wdno.nt', Path('./out/webdewey-nb.nt'))
    print("OK!")
