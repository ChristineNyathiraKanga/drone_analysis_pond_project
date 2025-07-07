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
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
# from dotenv import load_dotenv
import pytz
from io import BytesIO
# load_dotenv()
from twilio.rest import Client


api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=api_key)
gmail_pass = os.getenv("GMAIL_APP_PASSWORD")

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

def send_email_report(recommendation_data, recipient_emails, sender_email, sender_password):
    """
    Send pond recommendations as an HTML email to multiple recipients.
    """
    html = "<h2>Pond Water Level Recommendations</h2>"
    html += "<table border='1' cellpadding='5'><tr><th>Pond Category</th><th>Pond Name</th><th>Observation</th><th>Recommendation</th></tr>"
    for rec in recommendation_data:
        html += f"<tr><td>{rec.get('Pond Category', '')}</td><td>{rec['Pond Identifier']}</td><td>{rec['observations']}</td><td>{rec['Recommendation']}</td></tr>"
    html += "</table>"

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = ", ".join(recipient_emails)
    msg['Subject'] = "Pond Water Level Recommendations (PRIORITY)"
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_emails, msg.as_string())
            send_whatsapp_recommendations(recommendation_data)
        print("Email sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")
                   
def send_whatsapp_recommendations(recommendation_data, to_number=None):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM")
    to_number = to_number or os.getenv("TWILIO_WHATSAPP_TO")
    client = Client(account_sid, auth_token)

    for rec in recommendation_data:
        msg = (
            f"Pond Category: {rec.get('Pond Category', '')}\n"
            f"Pond Name: {rec.get('Pond Identifier', '')}\n"
            f"Observation: {rec.get('observations', '')}\n"
            f"Recommendation: {rec.get('Recommendation', '')}"
        )
        try:
            message = client.messages.create(
                body=msg,
                from_=from_number,
                to=to_number
            )
            print(f"WhatsApp message sent: SID {message.sid}")
        except Exception as e:
            print(f"Failed to send WhatsApp message: {e}")
            
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

def to_gsheet(pond_identity, observation, recommendation, pond_category):
    kenya_tz = pytz.timezone('Africa/Nairobi')
    current_datetime = datetime.now(kenya_tz)
    formatted_datetime = "VF-" + current_datetime.strftime("%Y-%m-%d-%H:%M")

    df = read_gsheet_from_url('https://docs.google.com/spreadsheets/d/11VxTUgviyL6ZnFY0x7yKgaT_e0Dxtaux18sckaUNbig/edit?gid=0#gid=0', 'Sheet1', 'pond-water-analysis-453506-8d3087dc5fe3.json')

    new_data = {
        'Pond Category': [pond_category],
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
    send_whatsapp_recommendations(recommendation_data)
    
def to_gsheet_batch(recommendation_data):
    kenya_tz = pytz.timezone('Africa/Nairobi')
    current_datetime = datetime.now(kenya_tz)
    formatted_datetime = "VF-" + current_datetime.strftime("%Y-%m-%d-%H:%M")

    df = read_gsheet_from_url('https://docs.google.com/spreadsheets/d/11VxTUgviyL6ZnFY0x7yKgaT_e0Dxtaux18sckaUNbig/edit?gid=0#gid=0', 'Sheet1', 'pond-water-analysis-453506-8d3087dc5fe3.json')

    new_data = []
    for recommendation in recommendation_data:
        new_data.append({
            'Pond Category': recommendation.get('Pond Category', ''),
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
    # --- Send email after writing to gsheet ---
    recipient_emails = [
        "christinek@victoryfarmskenya.com"
        # "nsogbuw@victoryfarmskenya.com",
        # "anneo@victoryfarmskenya.com",
        # "brendac@victoryfarmskenya.com"
    ]
    sender_email = "productionponds@gmail.com"
    sender_password = gmail_pass
    send_email_report(recommendation_data, recipient_emails, sender_email, sender_password)
    send_whatsapp_recommendations(recommendation_data)

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

def resize_image(image_file, max_size=1024):
    """Resize image to max_size (preserving aspect ratio) and return BytesIO."""
    try:
        image = Image.open(image_file)
        image.thumbnail((max_size, max_size))
        output = BytesIO()
        image.save(output, format="PNG")
        output.seek(0)
        return output
    except Exception as e:
        print(f"Error resizing image: {e}")
        return image_file  # fallback to original
    
def compare_images(prompt, image_1):
    resized_image = resize_image(image_1)
    data_url = change_image_format(resized_image)

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

async def async_compare_images(prompt, image_files, max_concurrent=15):
    """
    Process images in async batches to avoid overloading the server and hitting API limits.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    loop = asyncio.get_event_loop()

    async def process_image(image_file):
        async with semaphore:
            for attempt in range(3):
                try:
                    # Run compare_images in a thread to avoid blocking
                    result = await loop.run_in_executor(None, compare_images, prompt, image_file)
                    return result
                except Exception as e:
                    print(f"Error processing image: {e}. Retrying ({attempt+1}/3)...")
                    await asyncio.sleep(2)
            return None

    tasks = [process_image(img) for img in image_files]
    results = await asyncio.gather(*tasks)
    return results