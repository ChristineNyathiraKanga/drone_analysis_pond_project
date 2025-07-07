import os
import re
import urllib.parse
import requests
from msal import ConfidentialClientApplication
import base64

AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET_VALUE")

def get_access_token():
    app = ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
        client_credential=AZURE_CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    # print("Token result:", result)
    if not result or "access_token" not in result:
        raise RuntimeError(f"Could not obtain access token: {result}")
    return result["access_token"]

def extract_site_and_relative_path_from_link(link):
    link = urllib.parse.unquote(link)
    m = re.search(r"https://([^/]+)/(?:\:f:/r/)?sites/([^/]+)/(Shared Documents/.+)", link)
    if not m:
        raise ValueError("Invalid SharePoint link. Must contain /sites/{site}/Shared Documents/...")
    domain = m.group(1)
    site_name = m.group(2)
    relative_path = m.group(3).split('?', 1)[0]
    # print("Extracted:", domain, site_name, relative_path)
    return domain, site_name, relative_path


def sharing_url_to_share_id(sharing_url):
    """
    Converts a SharePoint sharing URL to Graph API share-id format.
    """
    url_bytes = sharing_url.encode("utf-8")
    b64_url = base64.urlsafe_b64encode(url_bytes).decode("utf-8").rstrip("=")
    return f"u!{b64_url}"

def list_sharepoint_images(sharepoint_link):
    """
    Accepts a SharePoint sharing link copied by user, returns download URLs of images inside.
    """
    token = get_access_token()
    share_id = sharing_url_to_share_id(sharepoint_link)
    url = f"https://graph.microsoft.com/v1.0/shares/{share_id}/driveItem"
    headers = {"Authorization": f"Bearer {token}"}
    # print("Resolving share link via Graph API:", url)
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    item = resp.json()

    if item["folder"] is None:
        raise ValueError("The provided link does not point to a folder.")

    drive_id = item["parentReference"]["driveId"]
    item_id = item["id"]

    # List children of the resolved folder
    folder_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/children"
    # print("Listing folder contents from:", folder_url)
    resp = requests.get(folder_url, headers=headers)
    # print("List status:", resp.status_code)
    # print("List text:", resp.text)
    resp.raise_for_status()
    items = resp.json().get("value", [])
    image_items = [
        item for item in items
        if item.get("file", {}).get("mimeType", "").startswith("image/")
    ]
    image_urls = [item["@microsoft.graph.downloadUrl"] for item in image_items]
    return image_items, image_urls
