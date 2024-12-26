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
from datetime import date, timedelta,datetime
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2 import service_account
from oauth2client.service_account import ServiceAccountCredentials
from urllib.error import URLError
from urllib3.exceptions import NewConnectionError, MaxRetryError
from requests.exceptions import ConnectionError
# from dotenv import load_dotenv

# load_dotenv()

api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=api_key)

prompt_v3 = """
            I will provide you with an image of a pond, the pond has a colored tube like structure in the middle, the colored tube is used to indicate water levels, colors are ordered as follow from top to bottom: 
            1. black plate , pond is full 
            2. green plate,  safe level no need for refill. 
            3. yellow plate , average risk still needs refill 
            4. red plate ,  critical level, urgent pond refill 

            your job 
                - Examine the image 
                - Identify all square plates visible and there colors. 
                - Based on the colors observed, assess the current water level of the pond. 
                - Please provide a brief explanation to justify your assessment.
                -  Based on the colors observed give the following recommendation and observations:
                            - if red,yellow, green and black are visible : 
                                recommendation: Urgent pond refill 
                                observation: Red
                            - if yellow, green and black are visible : 
                                recommendation: At risk, refill at next day cycle
                                observation: Yellow
                            - if green and black are visible :  
                                recommendation: No action needed
                                observation: Green
                            - if only black  : 
                                recommendation: no more filling
                                observation: Black
                - Return your evaluation as a JSON object in the following format:
                                        {\n  'Recommendation': <recommendation>'\n 'observations': <observations>}
                            - Do not add additional formatting or prefaces like ```json to the output.\n\nrespond in only valid json format only, dont add ``` or json"""


prompt_new = """
            I will provide you with an image of a pond the pond has colored Square plate-like structure in the middle, the colored square plate-like structure is used to indicate water levels, colors are ordered as follow from top to bottom: 
            1. black plate , pond is full 
            2. green plate,  safe level no need for refill. 
            3. yellow plate , average risk still needs refill 
            4. red plate ,  critical level, urgent pond refill 

            your job 
                - Examine the image 
                - Identify all square plates visible and there colors. 
                - Based on the colors observed, assess the current water level of the pond. 
                - Please provide a brief explanation to justify your assessment.
                -  Based on the colors observed give the following recommendation and observations:
                            - if red,yellow, green and black are visible : 
                                recommendation: Urgent pond refill 
                                observation: Red
                            - if yellow, green and black are visible : 
                                recommendation: At risk, refill at next day cycle
                                observation: Yellow
                            - if green and black are visible :  
                                recommendation: No action needed
                                observation: Green
                            - if only black  : 
                                recommendation: no more filling
                                observation: Black
                - Return your evaluation as a JSON object in the following format:
                                        {\n  'Recommendation': <recommendation>'\n 'observations': <observations>}
                            - Do not add additional formatting or prefaces like ```json to the output.\n\nrespond in only valid json format only, dont add ``` or json"""

prompt_old = """
            I will provide you with an image of a pond, the pond has a colored pillar in the middle, the colors are used to indicate water levels, colors are ordered as follow from top to bottom: 
            1. red color ,  pond is full  
            2. green color ,  average risk still needs refill. 
            
            Note: if bare concrete is seen after the 2 colors then critical level, urgent pond refill 
    

            your job 
                - Examine the image. 
                - Identify the pillar and the colors. 
                - Based on the colors observed, assess the current water level of the pond. 
                - Please provide a brief explanation to justify your assessment.
                -  Based on the colors observed give the following recommendation and observations:
                            - if bare concrete , green and red are visible  :
                                recommendation: Urgent pond refill 
                                observation: Concrete
                            - if green and red are visible : 
                                recommendation: At risk, refill at next day cycle
                                observation: Green
                            - if red only is visible : 
                                recommendation: no more filling
                                observation: Red
                            
                - Return your evaluation as a JSON object in the following format:
                                        {\n  'Recommendation': <recommendation>'\n 'observations': <observations>}
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


def send_whatsapp(message,number):
    access_token = 'EAAPNHSZBuZCdIBO0Hk4xBoqkvNz2XWr5o6gqtAnQE7a6nWfGXrQgb6dZA6p6oAMZABqf7adPZBGDZBB4ZBmGHQYBepqGV7orlcOzOBJDhmusnhEe219HbSKxytugJcFfFENoQmGMEzhhDYCl769boR50W6VD8CnQ3ROmpJEvCTB2Ib4Kysjt0jCdGZCerLUooZBR9KTTkKijPUwzNNGCZAgKqbhabN84w8bud3W25G'

    messenger = WhatsApp(access_token,  phone_number_id='415367251667765')
    messenger.send_message(message, number)


def read_gsheet_from_url(url, sheet_name, credential_path,skip_rows=0, skip_columns=0 ):
    '''
    Info on obtaining credentials: https://medium.com/@vince.shields913/reading-google-sheets-into-a-pandas-dataframe-with-gspread-and-oauth2-375b932be7bf
    
    url - an url of a gsheet,
    sheet_name - name of worksheet you want converted to a pd dataframe. Example: sheet_name='RESEARCH TABLE'
    skip_rows/skip_columns - numbers to be skipped
      - path to your credentials json file (I use a service account from my Google APIs project, also had to give it permission to read the needed sheets and enable Google Drive API for the project)
    
    '''
    credential_path = 'drone-project-445915-006e8606af11.json'
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file",
             "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
             credential_path, scope)

    trial = 1
    wait_secs = 30


    while True:
        try:
            gc = gspread.authorize(credentials)
            wks = gc.open_by_url(url).worksheet(sheet_name)
            data = wks.get_all_values()
            headers = data.pop(skip_rows)
            df = pd.DataFrame(data[(skip_rows):], columns=headers).iloc[:,skip_columns:]
            break


        except (TimeoutError,ConnectionError, NewConnectionError, MaxRetryError):

            if trial<4:

                print('failed to collect google sheets for {0} after {1} trial(s)\nTRYING AGAIN'.format(
                                                                                        sheet_name,
                                                                                        trial))
                time.sleep(wait_secs*trial)

                trial+=1    

            else:
                print('failed to collect google sheets for {0} after {1} trial(s)'.format(
                                                                                        sheet_name,
                                                                                        trial))
                raise

        except:
            raise




    time.sleep(5)
    return df

def write_to_gsheet(output,url, sheet_name,credential_path , clear_before_writing=True):
    #output = cal()
    output= output.replace(np.nan, '')
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']

    credentials = ServiceAccountCredentials.from_json_keyfile_name(
                 credential_path, scope)
    gc = gspread.authorize(credentials)
    worksheet = gc.open_by_url(url).worksheet(sheet_name)
    if clear_before_writing==True:
        worksheet.clear()
    worksheet.update([output.columns.values.tolist()] + output.values.tolist())

def to_gsheet(pond_identity,observation,recommendation): 
    current_datetime = datetime.now()
    current_datetime.strftime("%Y-%m-%d %H:%M:%S")

    df = read_gsheet_from_url('https://docs.google.com/spreadsheets/d/1X86bzukJnjsbhKGHammUAZDEit7XqIC-yf5uhVDbMtQ/edit?gid=0#gid=0','Sheet1','drone-project-445915-006e8606af11.json')

    new_data = {
        'Pond Name': [pond_identity],
        'Observation': [observation],
        'Recommendation': [recommendation]
    }
    new_df = pd.DataFrame(new_data)
    new_df['Date']=current_datetime

    # Append the new row to the existing DataFrame
    df = pd.concat([df, new_df], ignore_index=True)
    df['Date']=df['Date'].astype(str)

    write_to_gsheet(df,'https://docs.google.com/spreadsheets/d/1X86bzukJnjsbhKGHammUAZDEit7XqIC-yf5uhVDbMtQ/edit?gid=0#gid=0','Sheet1','drone-project-445915-006e8606af11.json')

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

def compare_images(prompt,image_1):

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