import os
import requests
import re
import base64
import json
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
# from twilio.rest import Client


api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=api_key)
gmail_pass = os.getenv("GMAIL_APP_PASSWORD")

prompt_v3 = """
            I will provide you with an image of a pond with a colored tube/gauge structure in the middle used to indicate water levels. The colored plates are arranged in a specific order from top to bottom:
            
            Color arrangement (top to bottom):
            1. WHITE plate (top) - pond is full 
            2. GREEN plate (second) - safe level, no need for refill
            3. BLUE plate (third) - average risk, still needs refill 
            4. RED plate (bottom) - critical level, urgent pond refill required

            Your job:
                - Examine the image carefully
                - Identify ALL colors visible on the gauge, considering different hues and lighting conditions
                - Consider water reflections which may appear as dirty green/brown hues that may reflect on the water
                - The water level is determined by which plates are visible above the water line
                - You must see ALL visible colored plates, not just focus on one color
                - Based on ALL colors observed, assess the current water level of the pond
                - Provide a brief explanation to justify your assessment
                - Use the WHITE plate as the primary visual anchor: it is usually the brightest/most visible and is always at the very top. Confirm WHITE first, then determine which plates below it are visible above water.

            Recommendation and observation rules based on ALL visible colors:
                - If RED, BLUE, GREEN, and WHITE plates are ALL visible above water:
                    recommendation: "Urgent pond refill"
                    observation: "Red"
                - If BLUE, GREEN, and WHITE plates are ALL visible above water:
                    recommendation: "Need to fill"
                    observation: "Blue"  
                - If GREEN and WHITE plates are visible above water:
                    recommendation: "No action needed"
                    observation: "Green"
                - Disambiguation: If only WHITE and a plate directly below it are visible and that second plate looks teal/cyan/blueish due to fading, lighting, or water refraction, classify it as GREEN (because the second plate is always GREEN). Only classify BLUE when the third plate position is clearly visible above water.
                - If only WHITE plate is visible above water:
                    recommendation: "No more filling"
                    observation: "White"

            Important notes:
                - Look for ALL colored plates that are visible above the water line
                - Always check color arrangement from top to bottom
                - Water reflections may show as dirty green/brown colors - do not confuse these with the actual colored plates
                - Green can sometimes appear as a bluish hue (teal/cyan) because of paint fading, camera exposure, or water refraction. When the plate immediately below WHITE appears bluish, treat it as GREEN unless the third plate (BLUE) is also clearly visible above water.
                - WHITE is typically the most reliable reference. If confidence is low for other colors, anchor on the visibility of the WHITE plate to set the minimum state; then refine based on additional clearly visible plates.
                - Base your assessment on the actual colored plates of the gauge, not water reflections

            Return your evaluation as a JSON object in the following format:
            {
              "Recommendation": "<recommendation>",
              "observations": "<observations>",
              "explanation": "<explanation>"
            }
            
            Respond in only valid JSON format. Do not add formatting like ```json or any other prefixes.
            """

def send_sms(receiver_list, msg, success_msg=True):
    """
    Send SMS to a list of phone numbers using environment-configured SMS gateway.
    """

    # If receiver_list is passed as JSON string, convert to list
    if isinstance(receiver_list, str):
        receiver_list = json.loads(receiver_list)
        if not isinstance(receiver_list, list):
            receiver_list = [receiver_list]

    # Optional: validate numbers format (basic)
    receiver_list = [str(num).strip() for num in receiver_list if str(num).startswith("+")]

    # Read credentials from environment
    sender_id = os.getenv("SMS_SENDER_ID")
    api_key = os.getenv("SMS_API_KEY")
    client_id = os.getenv("SMS_CLIENT_ID")
    sms_gateway_url = os.getenv("SMS_GATEWAY_URL")

    if not all([sender_id, api_key, client_id, sms_gateway_url]):
        raise ValueError("SMS configuration incomplete: check your environment variables.")

    # Construct request payload
    request_body = {
        "SenderId": sender_id,
        "MessageParameters": [
            {"Number": number, "Text": msg} for number in receiver_list
        ],
        "ApiKey": api_key,
        "ClientId": client_id
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    response = None

    try:
        response = requests.post(sms_gateway_url, json=request_body, headers=headers)
        response.raise_for_status()
        if success_msg:
            print(f"SMS sent successfully to: {receiver_list}")

    except requests.exceptions.RequestException as e:
        error_message = (
            f"Error sending SMS: {e}\n"
            f"Status Code: {response.status_code if response else 'N/A'}\n"
            f"Response Text: {response.text if response else 'N/A'}"
        )
        print(error_message)
        raise RuntimeError(error_message)


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
    
def send_sms_recommendations(recommendation_data):
    receiver_list = [
        "+254113572784",
        "+254796503765",
        "+254711810228",
        "+254724920866",
        "+254112952380",
        "+254111998026",
        "+254711811567",
        "+254711811569",
        "+254711811274"
    ]
    kenya_tz = pytz.timezone('Africa/Nairobi')
    current_datetime = datetime.now(kenya_tz)
    MAX_SMS_LENGTH = 1605
    recommendations_texts = []
    for idx, rec in enumerate(recommendation_data, 1):
        rec_msg = (
            f"\n--- Recommendation {idx} ---\n"
            f"Date: {current_datetime.strftime('%Y-%m-%d')}\n"
            f"Pond Name: {rec.get('Pond Identifier', '')}\n"
            f"Observation: {rec.get('observations', '')}\n"
            f"Recommendation: {rec.get('Recommendation', '')}\n"
        )
        recommendations_texts.append(rec_msg)

    chunks = []
    current_chunk = ""
    for rec_text in recommendations_texts:
        if len(current_chunk) + len(rec_text) <= MAX_SMS_LENGTH:
            current_chunk += rec_text
        else:
            chunks.append(current_chunk)
            current_chunk = rec_text

    if current_chunk:  # don't forget the last chunk
        chunks.append(current_chunk)

    total_parts = len(chunks)

    for idx, chunk_text in enumerate(chunks, 1):
        part_header = f"Part {idx}/{total_parts}\n"
        final_chunk = part_header + chunk_text

        try:
            send_sms(receiver_list, final_chunk)
            # print(f"\n--- SMS Part {idx}/{total_parts} ---\n{final_chunk}\n{'-'*40}")

            print(f"SMS Part {idx}/{total_parts} sent to {receiver_list}")
        except Exception as e:
            print(f"Failed to send SMS Part {idx}/{total_parts}: {e}")

 
def send_email_report(recommendation_data, recipient_emails, sender_email, sender_password):
    kenya_tz = pytz.timezone('Africa/Nairobi')
    current_datetime = datetime.now(kenya_tz)
    """
    Send pond recommendations as an HTML email to multiple recipients.
    """
    html = "<h2>Pond Water Level Recommendations</h2>"
    html += "<table border='1' cellpadding='5'><tr><th>Date</th><th>Pond Name</th><th>Observation</th><th>Recommendation</th></tr>"
    for rec in recommendation_data:
        html += f"<tr><td>{current_datetime.strftime('%Y-%m-%d')}</td><td>{rec['Pond Identifier']}</td><td>{rec['observations']}</td><td>{rec['Recommendation']}</td></tr>"
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
            # send_sms_recommendations(recommendation_data)
        print("Email sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")
                   
       
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
            
            # Handle duplicate column names by making them unique
            seen = {}
            unique_headers = []
            for header in headers:
                if header in seen:
                    seen[header] += 1
                    unique_headers.append(f"{header}_{seen[header]}")
                else:
                    seen[header] = 0
                    unique_headers.append(header)
            
            df = pd.DataFrame(data[(skip_rows):], columns=unique_headers).iloc[:, skip_columns:]
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
    # Handle NaN values and ensure the DataFrame is clean
    output = output.fillna('')  # Use fillna instead of replace for NaN values
    
    # Ensure no duplicate column names - custom implementation
    def make_unique_columns(columns):
        seen = {}
        unique_cols = []
        for col in columns:
            if col in seen:
                seen[col] += 1
                unique_cols.append(f"{col}.{seen[col]}")
            else:
                seen[col] = 0
                unique_cols.append(col)
        return unique_cols
    
    output.columns = make_unique_columns(output.columns)
    
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

    df = read_gsheet_from_url('https://docs.google.com/spreadsheets/d/11VxTUgviyL6ZnFY0x7yKgaT_e0Dxtaux18sckaUNbig/edit?gid=0#gid=0', 'Input', 'pond-water-analysis-453506-8d3087dc5fe3.json')

    new_data = {
        'Pond Category': [pond_category],
        'Pond Name': [pond_identity],
        'Observation': [observation],
        'Recommendation': [recommendation]
    }
    new_df = pd.DataFrame(new_data)
    new_df['Date'] = formatted_datetime

    # Append the new row to the existing DataFrame
    try:
        df = pd.concat([df, new_df], ignore_index=True)
    except ValueError as e:
        if "Reindexing only valid with uniquely valued Index objects" in str(e):
            # Reset indices and try again
            df = df.reset_index(drop=True)
            new_df = new_df.reset_index(drop=True)
            df = pd.concat([df, new_df], ignore_index=True)
        else:
            raise e
    df['Date'] = df['Date'].astype(str)

    write_to_gsheet(df, 'https://docs.google.com/spreadsheets/d/11VxTUgviyL6ZnFY0x7yKgaT_e0Dxtaux18sckaUNbig/edit?gid=0#gid=0', 'Input', 'pond-water-analysis-453506-8d3087dc5fe3.json')
    print('done')
    
def to_gsheet_batch(recommendation_data):
    kenya_tz = pytz.timezone('Africa/Nairobi')
    current_datetime = datetime.now(kenya_tz)
    formatted_datetime = "VF-" + current_datetime.strftime("%Y-%m-%d-%H:%M")

    df = read_gsheet_from_url('https://docs.google.com/spreadsheets/d/11VxTUgviyL6ZnFY0x7yKgaT_e0Dxtaux18sckaUNbig/edit?gid=0#gid=0', 'Input', 'pond-water-analysis-453506-8d3087dc5fe3.json')

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
    
    if not df.empty and not new_df.empty:
        all_columns = list(df.columns) + [col for col in new_df.columns if col not in df.columns]
        df = df.reindex(columns=all_columns, fill_value='')
        new_df = new_df.reindex(columns=all_columns, fill_value='')

    try:
        df = pd.concat([df, new_df], ignore_index=True)
    except ValueError as e:
        if "Reindexing only valid with uniquely valued Index objects" in str(e):
            df = df.reset_index(drop=True)
            new_df = new_df.reset_index(drop=True)
            df = pd.concat([df, new_df], ignore_index=True)
        else:
            raise e
    df['Date'] = df['Date'].astype(str)

    write_to_gsheet(df, 'https://docs.google.com/spreadsheets/d/11VxTUgviyL6ZnFY0x7yKgaT_e0Dxtaux18sckaUNbig/edit?gid=0#gid=0', 'Input', 'pond-water-analysis-453506-8d3087dc5fe3.json')

    # print('done')
    # --- Send email after writing to gsheet ---
    recipient_emails = [
        "christinek@victoryfarmskenya.com",
        "nsogbuw@victoryfarmskenya.com",
        "anneo@victoryfarmskenya.com",
        "brendac@victoryfarmskenya.com",
        "philipa@victoryfarmskenya.com",
        "colvina@victoryfarmskenya.com",
        "irenem@victoryfarmskenya.com",
        "steve.moran@victoryfarmskenya.com",
        "edna@victoryfarmskenya.com",
        "Narcisos@victoryfarmskenya.com",
        "Norman@victoryfarmskenya.com",
        "nchew@victoryfarmskenya.com",
        "Orlandod@victoryfarmskenya.com",
        "georgiah@victoryfarmskenya.com",
        "joseph.rehmann@victoryfarmskenya.com"
    ]
    sender_email = "productionponds@gmail.com"
    sender_password = gmail_pass
    # send_email_report(recommendation_data, recipient_emails, sender_email, sender_password)
    send_sms_recommendations(recommendation_data)

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