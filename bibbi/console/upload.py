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


def upload_cmd(config, options):
    session = requests.Session()
    session.headers.update({'apikey': config.ingest_apikey})
    retries = Retry(total=3,
                    backoff_factor=0.1,
                    status_forcelist=[429, 500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))

    # -Upload graphs ----

    if not options.skip_vocabularies:

        graphs = {
            'bibbi.nt': 'https://graph.bs.no/bibbi',
            'webdewey-nb.nt': 'https://graph.bs.no/webdewey',
            'webdewey-bibbi-mappings.nt': 'https://graph.bs.no/webdewey',
        }

        print("Ready")

        files = [
            ('files', (basename(file), open(file, 'rb')))
            for file in config.dest_dir.glob('*.nt')
        ]

        # files = [
        #     ('files', (basename(file), open(file, 'rb')))
        #     for file in ['out/bibbi-genre.nt']
        # ]

        datasets = [
            {'graph': graphs[file[1][0]], 'filename': file[1][0]}
            for file in files
            if file[1][0].endswith('.nt')
        ]

        host = 'https://lds.bs.no/api/graphs'
        # host = 'http://9c3613e50326.ngrok.io/update-graphs'

        response = session.post(host,
                                data={
                                    'datasets': json.dumps(datasets)
                                },
                                files=files)

        response.raise_for_status()

        print(response)

        log.info("Done uploading %d files" % len(files))

    # -Upload catalog ----

    if not options.skip_catalog:

        catalog_file = config.dest_dir.joinpath('catalog.jsonl')

        host = 'https://lds.bs.no/api/catalog'
        response = session.post(host, files={'file': catalog_file.open('rb') })
        print(response.text)
        response.raise_for_status()
        print(response)

        log.info("Done uploading catalog")
