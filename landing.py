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
from reed_analyse import *
from zipfile import ZipFile
import os
from concurrent.futures import ThreadPoolExecutor
import tempfile

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

def process_image(image_file, prompt, temp_dir):
    pond_identifier = os.path.splitext(image_file)[0]
    image_path = os.path.join(temp_dir, image_file)
    with open(image_path, "rb") as img:
        try:
            data = compare_images(prompt, img)
            d = json.loads(data)
            d["Pond Identifier"] = pond_identifier
            return d
        except Exception as e:
            st.error(f'Error processing {image_file}: {e}')
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
                except Exception:
                    st.error('KINDLY REFRESH THE BROWSER AND TRY AGAIN!!!')

        try:
            with buff:
                st.image(
                    uploaded_file,
                    caption=search_query,
                    use_container_width=True,
                )
                st.header(f'Summary: {search_query}')
                f_d = st.session_state["recommendation_data"]
                display_similarities('Observation', f_d['observations'])
                display_similarities('Recommendation', f_d['Recommendation'])
                to_gsheet(f_d['observations'], f_d['Recommendation'])
                # print(f_d)
        except:
            st.error('KINDLY REFRESH THE BROWSER AND TRY AGAIN !!! ')

if submit_button_batch:
    if uploaded_folder is None:
        st.error("Please upload a ZIP folder containing image files.")
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            with ZipFile(uploaded_folder, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            image_files = [f for f in os.listdir(temp_dir) if f.endswith(('png', 'jpg', 'jpeg', 'PNG', 'JPG', 'JPEG'))]
            if not image_files:
                st.error("No valid image files found in the uploaded folder.")
            else:
                st.session_state["recommendation_data"] = []
                prompt = get_prompt(submit_button_batch)

                with ThreadPoolExecutor() as executor:
                    futures = [executor.submit(process_image, image_file, prompt, temp_dir) for image_file in image_files]
                    for future in futures:
                        result = future.result()
                        if result:
                            st.session_state["recommendation_data"].append(result)

                for recommendation in st.session_state["recommendation_data"]:
                    st.image(
                        os.path.join(temp_dir, recommendation["Pond Identifier"] + ".jpg"),
                        caption=recommendation["Pond Identifier"],
                        use_container_width=True,
                    )
                    st.header(f'Summary: {recommendation["Pond Identifier"]}')
                    display_similarities('Observation', recommendation['observations'])
                    display_similarities('Recommendation', recommendation['Recommendation'])

                    # Display the JSON array of all recommendations
                    # st.json(st.session_state["recommendation_data"])
                    # print(json.dumps(st.session_state["recommendation_data"], indent=4))

                    # Write to Google Sheet
                    to_gsheet_batch(st.session_state["recommendation_data"])