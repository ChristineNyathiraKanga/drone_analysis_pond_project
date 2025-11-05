import streamlit as st
import numpy as np
import datetime
import re
from functools import partial
import requests
import pandas as pd
from datetime import date, timedelta, datetime
import time
import json
from zipfile import ZipFile
import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import asyncio
from PIL import Image  # Use Pillow instead of PIL
from reed_analyse import *
from sharepoint_utils import list_sharepoint_images

st.set_page_config(layout="wide")

st.markdown("<h1 style='text-align: center; color: grey;'> Pond Water Level Analysis </h1>", unsafe_allow_html=True)
buff, col = st.columns([10, 1])

def display_similarities(heading, infomation):
    st.subheader(f"{heading}:", divider='rainbow')
    st.write(f"- {infomation}")

initialize_session_state()

def safe_json_loads(s):
    # Replace single quotes with double quotes for property names and string values
    s = re.sub(r"(?<!\\)'", '"', s)
    try:
        return json.loads(s)
    except Exception as e:
        return None

def extract_category_and_identifier(file_path):
    parts = file_path.replace("\\", "/").split("/")
    if len(parts) >= 2:
        pond_category = parts[0]
        pond_identifier = os.path.splitext(parts[1])[0]
    else:
        pond_category = ""
        pond_identifier = os.path.splitext(parts[0])[0]
    return pond_category, pond_identifier


# Helper function to get the appropriate prompt
def get_prompt(submit_button):
    if submit_button:
        st.session_state["pond_prompt"] = prompt_v3
        return prompt_v3
    else:
        return None
    
async def process_images_in_batches(prompt, image_files, batch_size=10, max_concurrent=2):
    """
    Process images in batches to avoid memory overload and timeouts.
    """
    all_results = []
    total = len(image_files)
    for i in range(0, total, batch_size):
        batch = image_files[i:i+batch_size]
        results = await async_compare_images(prompt, batch, max_concurrent=max_concurrent)
        all_results.extend(results)
        print(f"Processed batch {i//batch_size+1} of {((total-1)//batch_size)+1}")
    return all_results


def process_image(image_file, prompt):
    pond_identifier = os.path.splitext(image_file.name)[0]
    image = Image.open(image_file)
    with BytesIO() as img_buffer:
        image.save(img_buffer, format=image.format)
        img_buffer.seek(0)
        try:
            data = compare_images(prompt, img_buffer)
            d = json.loads(data)
            d["Pond Identifier"] = pond_identifier
            return d
        except Exception as e:
            st.error(f'Error processing {image_file.name}: {e}')
            return None

with st.sidebar:
    with st.expander("Single Image Processing"):
        uploaded_file = st.file_uploader("Select or drag an image file here", type=['png', 'jpg', 'jpeg','JPG','PNG','JPEG'])
        st.session_state["uploaded_image"] = uploaded_file
        search_query = st.text_input("Enter pond number/identifier")
        pond_category = st.selectbox("Select Pond Category", ['Heap 1 ponds','Heap 2 ponds','Broodstock ponds','Nursery ponds'])
        submit_button_single = st.button("Analyse Tube Structure for Image")
    
    with st.expander("Batch Processing (SharePoint Link)"):
        sharepoint_link = st.text_input("Paste SharePoint folder link containing images")
        submit_button_batch = st.button("Analyse Tube Structures from SharePoint")

if submit_button_single:
    if uploaded_file is None:
        st.error("Please upload an image file.")
    elif not search_query:
        st.error("Please enter a pond number/identifier.")
    else:
        prompt = get_prompt(submit_button_single)
        if prompt is not None:
            try:
                result = compare_images(prompt, uploaded_file)
                d = safe_json_loads(result)
                if d:
                    d["Pond Category"] = pond_category
                    d["Pond Identifier"] = search_query
                    st.session_state["recommendation_data"] = [d]

                    # Show results
                    st.image(
                        uploaded_file,
                        caption=search_query,
                        use_container_width=True,
                    )
                    st.header(f'Summary: {d["Pond Identifier"]}')
                    display_similarities('Observation', d['observations'])
                    display_similarities('Recommendation', d['Recommendation'])
                    display_similarities('Explanation', d['explanation'])

                    # Write to Google Sheet
                    to_gsheet(d["Pond Identifier"], d["observations"], d["Recommendation"], d["Pond Category"])
                    
                    # Optionally send email for single image
                    recipient_emails = [
                        "christinek@victoryfarmskenya.com",
                        "nsogbuw@victoryfarmskenya.com",
                        "anneo@victoryfarmskenya.com",
                        "brendac@victoryfarmskenya.com"
                    ]
                    sender_email = "productionponds@gmail.com"
                    sender_password = gmail_pass
                    send_email_report([d], recipient_emails, sender_email, sender_password)
                else:
                    st.error("Could not parse the result as JSON.")
            except Exception as e:
                st.error(f"Error processing image: {e}")

# Batch processing for SharePoint images
if submit_button_batch:
    if not sharepoint_link:
        st.error("Please provide a SharePoint folder link.")
    else:
        try:
            st.info("Fetching image URLs from SharePoint...")
            image_items, image_urls = list_sharepoint_images(sharepoint_link)
            if not image_urls:
                st.error("No image files found in the provided SharePoint folder.")
            else:
                st.session_state["recommendation_data"] = []
                prompt = get_prompt(submit_button_batch)

                async def process_sharepoint_images(prompt, image_urls):
                    import aiohttp
                    results = []
                    async with aiohttp.ClientSession() as session:
                        for url in image_urls:
                            async with session.get(url) as resp:
                                if resp.status == 200:
                                    img_bytes = await resp.read()
                                    img_file = BytesIO(img_bytes)
                                    result = await async_compare_images(prompt, [img_file], max_concurrent=1)
                                    results.extend(result)
                                else:
                                    results.append(None)
                    return results

                results = asyncio.run(process_sharepoint_images(prompt, image_urls))
                for idx, result in enumerate(results):
                    if result:
                        d = safe_json_loads(result)
                        if d:
                            item = image_items[idx]
                            pond_identifier = os.path.splitext(item["name"])[0]
                            pond_category = item["parentReference"]["name"]
                            image_url = item["@microsoft.graph.downloadUrl"]

                            d["Pond Identifier"] = pond_identifier
                            d["Pond Category"] = pond_category
                            d["File Path"] = image_url
                            st.session_state["recommendation_data"].append(d)
                        else:
                            st.error(f"Error parsing result for image {idx+1}: Invalid JSON\nRaw result: {result}")

                for recommendation in st.session_state["recommendation_data"]:
                    image_url = recommendation.get("File Path", None)
                    if image_url:
                        st.image(image_url, caption=recommendation["Pond Identifier"], use_container_width=True)
                        st.header(f'Summary: {recommendation["Pond Identifier"]}')
                        display_similarities('Observation', recommendation['observations'])
                        display_similarities('Recommendation', recommendation['Recommendation'])
                        display_similarities('Explanation', d['explanation'])
                    else:
                        st.error(f"Image for {recommendation['Pond Identifier']} not found.")
                to_gsheet_batch(st.session_state["recommendation_data"])
        except Exception as e:
            st.error(f"Error fetching or processing images: {e}")