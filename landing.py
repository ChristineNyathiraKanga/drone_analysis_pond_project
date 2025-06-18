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

st.set_page_config(layout="wide")

st.markdown("<h1 style='text-align: center; color: grey;'> Pond Water Level Analysis </h1>", unsafe_allow_html=True)
buff, col = st.columns([10, 1])

def display_similarities(heading, infomation):
    st.subheader(f"{heading}:", divider='rainbow')
    st.write(f"- {infomation}")

initialize_session_state()

# Helper function to get the appropriate prompt
def get_prompt(submit_button):
    if submit_button:
        st.session_state["pond_prompt"] = prompt_v3
        return prompt_v3
    else:
        return None

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
        uploaded_file = st.file_uploader("Select or drag an image file here", type=['png', 'jpg', 'jpeg'])
        st.session_state["uploaded_image"] = uploaded_file
        search_query = st.text_input("Enter pond number/identifier")
        submit_button_single = st.button("Analyse Tube Structure for Image")

    with st.expander("Batch Processing"):
        uploaded_folder = st.file_uploader("Select or drag a ZIP folder with image files here", type=['zip'])
        st.session_state["uploaded_folder"] = uploaded_folder
        submit_button_batch = st.button("Analyse Tube Structures")

if submit_button_single:
    if uploaded_file is None:
        st.error("Please upload an image file.")
    elif not search_query:
        st.error("Please enter a pond number/identifier.")
    else:
        prompt = get_prompt(submit_button_single)
        if prompt is not None:
            try:
                st.session_state["recommendation_data"] = {}
                data = compare_images(prompt, uploaded_file)
                d = json.loads(data)
                st.session_state["recommendation_data"] = d
                to_gsheet(search_query, d['observations'], d['Recommendation'])
            except Exception as e:
                st.error(f'Error: {e}')
                try:
                    data = compare_images(prompt, uploaded_file)
                    d = json.loads(data)
                    st.session_state["recommendation_data"] = d
                    to_gsheet(search_query, d['observations'], d['Recommendation'])
                except Exception as e:
                    st.error(f'Error: {e}')
                    # st.error('KINDLY REFRESH THE BROWSER AND TRY AGAIN!!!')

        try:
            st.image(
                uploaded_file,
                caption=search_query,
                use_container_width=True,
            )
            st.header(f'Summary: {search_query}')
            f_d = st.session_state["recommendation_data"]
            display_similarities('Observation', f_d['observations'])
            display_similarities('Recommendation', f_d['Recommendation'])
            print(f_d)
        except Exception as e:
            st.error(f'Error: {e}')
            st.error('KINDLY REFRESH THE BROWSER AND TRY AGAIN !!! ')

if submit_button_batch:
    if uploaded_folder is None:
        st.error("Please upload a ZIP folder containing image files.")
    else:
        with ZipFile(uploaded_folder, 'r') as zip_ref:
            image_files = [f for f in zip_ref.namelist() if f.endswith(('png', 'jpg', 'jpeg', 'PNG', 'JPG', 'JPEG'))]
            if not image_files:
                st.error("No valid image files found in the uploaded folder.")
            else:
                st.session_state["recommendation_data"] = []
                prompt = get_prompt(submit_button_batch)

                # Prepare file-like objects for async processing
                image_file_objs = [zip_ref.open(image_file) for image_file in image_files]

                # Use async batch processing
                results = asyncio.run(async_compare_images(prompt, image_file_objs, max_concurrent=5))
                for idx, result in enumerate(results):
                    if result:
                        try:
                            d = json.loads(result)
                            d["Pond Identifier"] = os.path.splitext(image_files[idx])[0]
                            st.session_state["recommendation_data"].append(d)
                        except Exception as e:
                            st.error(f"Error parsing result for {image_files[idx]}: {e}")

                for recommendation in st.session_state["recommendation_data"]:
                    image_file = next((f for f in image_files if os.path.splitext(f)[0] == recommendation["Pond Identifier"]), None)
                    if image_file:
                        with zip_ref.open(image_file) as img_file:
                            image = Image.open(img_file)
                            st.image(
                                image,
                                caption=recommendation["Pond Identifier"],
                                use_container_width=True,
                            )
                        st.header(f'Summary: {recommendation["Pond Identifier"]}')
                        display_similarities('Observation', recommendation['observations'])
                        display_similarities('Recommendation', recommendation['Recommendation'])
                    else:
                        st.error(f"Image file for {recommendation['Pond Identifier']} not found.")

                # Write to Google Sheet
                to_gsheet_batch(st.session_state["recommendation_data"])