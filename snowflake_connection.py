import os

import snowflake.connector
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv

load_dotenv()


def _load_private_key():
    # Local dev points SNOWFLAKE_PRIVATE_KEY_PATH at a .p8 file on disk. A hosted
    # deployment (e.g. Streamlit Community Cloud) has no such file - its secrets
    # panel can only hand over the key's own PEM text, via SNOWFLAKE_PRIVATE_KEY.
    # Support both without changing existing local behaviour (that env var is
    # simply unset locally, so the file-path branch below still runs exactly as
    # before).
    key_content = os.environ.get("SNOWFLAKE_PRIVATE_KEY")
    if key_content:
        # Some secrets UIs collapse real newlines to literal "\n" - restore them.
        key_bytes = key_content.replace("\\n", "\n").encode("utf-8")
    else:
        key_path = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
        with open(key_path, "rb") as f:
            key_bytes = f.read()
    private_key = serialization.load_pem_private_key(key_bytes, password=None)
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def get_connection(schema=None):
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=_load_private_key(),
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=schema or os.environ["SNOWFLAKE_SCHEMA"],
    )
