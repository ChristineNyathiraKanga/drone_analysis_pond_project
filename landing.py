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

st.set_page_config(layout="wide")

st.markdown("<h1 style='text-align: center; color: grey;'> Pond Water Level Analysis </h1>", unsafe_allow_html=True)
buff, col = st.columns([10, 1])

def display_similarities(heading,infomation):
    st.subheader(f"{heading}:",divider='rainbow')
    st.write(f"- {infomation}") 

initialize_session_state()

    # Helper function to get the appropriate prompt
def get_prompt(submit_button_new3):
    if submit_button_new3:
        st.session_state["pond_prompt"] = prompt_v3
        return prompt_v3

    else:
        return None

with st.sidebar:
    
    uploaded_file = st.file_uploader("Select or drag an image file here", type=['png', 'jpg', 'jpeg'])
   

    st.session_state["uploaded_image"] = uploaded_file

    search_query = st.text_input("Enter pond number/identifier")

    submit_button_new3 = st.button("Analyse Tube Structure")

    # Check if a file is uploaded and either button is pressed
    if uploaded_file is not None and (submit_button_new3):

        prompt = get_prompt(submit_button_new3)

        if prompt is not None:
            try:
                st.session_state["recommendation_data"] = {}

                # Process using the selected prompt
                data = compare_images(prompt, uploaded_file)
                d = json.loads(data)
                st.session_state["recommendation_data"] = d

            except Exception as e:
                st.error(f'Error: {e}')
                try:
                    # Retry processing using the same prompt in case of failure
                    data = compare_images(prompt, uploaded_file)
                    d = json.loads(data)
                    st.session_state["recommendation_data"] = d
                except Exception:
                    st.error('KINDLY REFRESH THE BROWSER AND TRY AGAIN!!!')
        else:
            st.error("Please press either 'Analyse New Pillar Structure' or 'Analyse Old Pillar Structure'.")

    
        try: 
            with buff:

                st.image(
                    uploaded_file,
                    caption=search_query,
                    use_container_width=True,
                )

                st.header('Summary')
                f_d= st.session_state["recommendation_data"]
                display_similarities('Observation',f_d['observations'])
                display_similarities('Recommendation',f_d['Recommendation'])
                # message = search_query + ": "+ f_d['Recommendation'] 
                # print(message)
                # numbers = ['254724467676','254790751380','254754419139']
                # for number in numbers:
                #     send_whatsapp(message,number)
                #uncomment line bellow after adding google sheet credentials follow link: https://medium.com/@vince.shields913/reading-google-sheets-into-a-pandas-dataframe-with-gspread-and-oauth2-375b932be7bf
                # to_gsheet(search_query,f_d['observations'],f_d['Recommendation'])

        except:
            st.error('KINDLY REFRESH THE BROWSER AND TRY AGAIN !!! ')
           
         


               