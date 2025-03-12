import os
import requests
import re
import base64
import openai
from openai import OpenAI
import pandas as pd
import numpy as np
import time
from PIL import Image
import streamlit as st
from heyoo import WhatsApp
import gspread
from datetime import date, timedelta, datetime
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2 import service_account
from urllib.error import URLError
from urllib3.exceptions import NewConnectionError, MaxRetryError
from requests.exceptions import ConnectionError
# from dotenv import load_dotenv
import pytz
# load_dotenv()

api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=api_key)

prompt_v3 = """
            I will provide you with an image of a pond, the pond has a colored tube like structure in the middle, the colored tube is used to indicate water levels, colors are ordered as follow from top to bottom: 
            1. white plate , pond is full 
            2. green plate,  safe level no need for refill. 
            3. blue plate , average risk still needs refill 
            4. red plate ,  critical level, urgent pond refill 

            your job 
                - Examine the image 
                - Identify all colors visible considering factors of different hues of the colors. 
                - Based on the colors observed, assess the current water level of the pond. 
                - Please provide a brief explanation to justify your assessment.
                -  Based on the colors observed give the following recommendation and observations:
                            - if red, blue, green and white are visible : 
                                recommendation: Urgent pond refill 
                                observation: Red
                            - if blue, green and white are visible : 
                                recommendation: At risk, refill at next day cycle
                                observation: Blue
                            - if green and white are visible :  
                                recommendation: No action needed
                                observation: Green
                            - if only white  : 
                                recommendation: no more filling
                                observation: White
                - Return your evaluation as a JSON object in the following format:
                                        {\n  'Recommendation': <recommendation>'\n 'observations': <observations> '\n 'explanation': <explanation> }
                            - Do not add additional formatting or prefaces like ```json to the output.\n\nrespond in only valid json format only, dont add ``` or json"""

def initialize_session_state():
    """
         Initializes all necessary session state for storing data across multiple clicks
    """
    if "pond_prompt" not in st.session_state:
        st.session_state["pond_prompt"] = {}

    if "uploaded_image" not in st.session_state:
        st.session_state["uploaded_image"] = {}

    if "recommendation_data" not in st.session_state:
        st.session_state["recommendation_data"] = {}

def send_whatsapp(message, number):
    access_token = os.getenv('WHATSAPP_ACCESS_TOKEN')
    messenger = WhatsApp(access_token, phone_number_id='415367251667765')
    messenger.send_message(message, number)

def read_gsheet_from_url(url, sheet_name, credential_path, skip_rows=0, skip_columns=0):
    credential_path = 'pond-water-analysis-453506-8d3087dc5fe3.json'
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file",
             "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(credential_path, scope)

    trial = 1
    wait_secs = 30

    while True:
        try:
            gc = gspread.authorize(credentials)
            wks = gc.open_by_url(url).worksheet(sheet_name)
            data = wks.get_all_values()
            headers = data.pop(skip_rows)
            df = pd.DataFrame(data[(skip_rows):], columns=headers).iloc[:, skip_columns:]
            break
        except (TimeoutError, ConnectionError, NewConnectionError, MaxRetryError):
            if trial < 4:
                print(f'Failed to collect google sheets for {sheet_name} after {trial} trial(s)\nTRYING AGAIN')
                time.sleep(wait_secs * trial)
                trial += 1
            else:
                print(f'Failed to collect google sheets for {sheet_name} after {trial} trial(s)')
                raise
        except:
            raise

    time.sleep(5)
    return df

def write_to_gsheet(output, url, sheet_name, credential_path, clear_before_writing=True):
    output = output.replace(np.nan, '')
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(credential_path, scope)
    gc = gspread.authorize(credentials)
    worksheet = gc.open_by_url(url).worksheet(sheet_name)
    if clear_before_writing:
        worksheet.clear()
    worksheet.update([output.columns.values.tolist()] + output.values.tolist())

def to_gsheet(pond_identity, observation, recommendation):
    kenya_tz = pytz.timezone('Africa/Nairobi')
    current_datetime = datetime.now(kenya_tz)
    formatted_datetime = "VF-" + current_datetime.strftime("%Y-%m-%d-%H:%M")

    df = read_gsheet_from_url('https://docs.google.com/spreadsheets/d/11VxTUgviyL6ZnFY0x7yKgaT_e0Dxtaux18sckaUNbig/edit?gid=0#gid=0', 'Sheet1', 'pond-water-analysis-453506-8d3087dc5fe3.json')

    new_data = {
        'Pond Name': [pond_identity],
        'Observation': [observation],
        'Recommendation': [recommendation]
    }
    new_df = pd.DataFrame(new_data)
    new_df['Date'] = formatted_datetime

    # Append the new row to the existing DataFrame
    df = pd.concat([df, new_df], ignore_index=True)
    df['Date'] = df['Date'].astype(str)

    write_to_gsheet(df, 'https://docs.google.com/spreadsheets/d/11VxTUgviyL6ZnFY0x7yKgaT_e0Dxtaux18sckaUNbig/edit?gid=0#gid=0', 'Sheet1', 'pond-water-analysis-453506-8d3087dc5fe3.json')

    print('done')

def to_gsheet_batch(recommendation_data):
    kenya_tz = pytz.timezone('Africa/Nairobi')
    current_datetime = datetime.now(kenya_tz)
    formatted_datetime = "VF-" + current_datetime.strftime("%Y-%m-%d-%H:%M")

    df = read_gsheet_from_url('https://docs.google.com/spreadsheets/d/11VxTUgviyL6ZnFY0x7yKgaT_e0Dxtaux18sckaUNbig/edit?gid=0#gid=0', 'Sheet1', 'pond-water-analysis-453506-8d3087dc5fe3.json')

    new_data = []
    for recommendation in recommendation_data:
        new_data.append({
            'Pond Name': recommendation['Pond Identifier'],
            'Observation': recommendation['observations'],
            'Recommendation': recommendation['Recommendation'],
            'Date': formatted_datetime
        })

    new_df = pd.DataFrame(new_data)

    # Append the new rows to the existing DataFrame
    df = pd.concat([df, new_df], ignore_index=True)
    df['Date'] = df['Date'].astype(str)

    write_to_gsheet(df, 'https://docs.google.com/spreadsheets/d/11VxTUgviyL6ZnFY0x7yKgaT_e0Dxtaux18sckaUNbig/edit?gid=0#gid=0', 'Sheet1', 'pond-water-analysis-453506-8d3087dc5fe3.json')

    print('done')

def change_image_format(image_file):
    """Convert an uploaded image file to a base64-encoded data URL."""
    try:
        # Read the content of the image
        image_content = image_file.read()

        # Encode the image to base64
        base64_image = base64.b64encode(image_content).decode('utf-8')

        # Create the data URL format
        data_url = f"data:image/png;base64,{base64_image}"
        return data_url
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def compare_images(prompt, image_1):
    data_url = change_image_format(image_1)

    response = client.chat.completions.create(model="gpt-4o",
    messages=[
        {
        "role": "user",
        "content": [
            {
            "type": "text",
            "text": prompt
            },
            {
            "type": "image_url",
            "image_url": {
                "url": f"{data_url}"
            }
            }
        ]
        }
    ],
    temperature=0,
    max_tokens=2048,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0)
    response_text = response.choices[0].message.content
    return response_text