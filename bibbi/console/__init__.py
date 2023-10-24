import argparse
from dotenv import load_dotenv
from pathlib import Path

from .update_webdewey import update_webdewey_cmd
from .upload import upload_cmd
from .extract_catalog import extract_catalog
from .extract_authorities import extract_authorities
from .config import Config
from bibbi.logging import configure_logging


def add_upload_parser(subparsers):
    parser = subparsers.add_parser('upload')
    parser.set_defaults(func=upload_cmd)
    parser.add_argument('--skip-vocabularies', action='store_true', default=False)
    parser.add_argument('--skip-catalog', action='store_false', default=True)


def add_update_webdewey_parser(subparsers):
    parser = subparsers.add_parser('update_webdewey')
    parser.set_defaults(func=update_webdewey_cmd)


def add_catalog_parser(subparsers):
    parser = subparsers.add_parser('catalog')
    parser.set_defaults(func=extract_catalog)
    parser.add_argument('--no-cache', action='store_true', default=False)


def add_authorities_parser(subparsers):
    parser = subparsers.add_parser('authorities')
    parser.set_defaults(func=extract_authorities)
    parser.add_argument('--use-cache', action='store_true', default=False)
    parser.add_argument('--remove-unused', action='store_true', default=False)


def app():
    load_dotenv()

    configure_logging()

    config = Config(
        dest_dir=Path('./out'),
        ingest_apikey='mOlW4b734-s28G5UtpO2+I5g8aDo0u376sB_/Vn8v2UO2VTkH'
    )

    parser = argparse.ArgumentParser(description='Promus data exporter')
    subparsers = parser.add_subparsers()

    add_upload_parser(subparsers)
    add_update_webdewey_parser(subparsers)
    add_catalog_parser(subparsers)
    add_authorities_parser(subparsers)

    args = parser.parse_args()

    # Update config from args if needed

    args.func(config, args)
