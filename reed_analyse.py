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
import pytz
from io import BytesIO
import cv2
from dotenv import load_dotenv
load_dotenv()
# from twilio.rest import Client


api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=api_key)
gmail_pass = os.getenv("GMAIL_APP_PASSWORD")

prompt_v3 = """
            I will provide you with an image of a pond with a colored tube/gauge structure in the middle used to indicate water levels. You are analyzing an image of a fish pond that contains a vertical colored gauge/tube used to indicate the pond’s water level.
            The gauge has 4 colored plates arranged in a fixed order from **top to bottom** as follows:
            
            1. WHITE plate (top) - pond is FULL 
            2. GREEN plate (second) - SAFE level, no need for refill
            3. BLUE plate (third) - AVERAGE RISK, still needs refill
            4. RED plate (bottom) - CRITICAL level, urgent pond refill required

            Your task is to identify the current visible plates above the water line and determine the pond`s water level status.
            
            Visual Analysis Rules:

            1. Always start from the top (WHITE) and move downward.
            - Confirm whether the WHITE plate is visible first — it is always at the top.
            - Then check for GREEN, then BLUE, then RED in that order.

            2. Positional logic override:
            - The plates’ order never changes.  
                Therefore, if a color appears out of sequence (e.g. BLUE above GREEN), it must be due to reflection or lighting error — ignore that anomaly.

            3. Reflection handling:
            - Water and nets may create greenish, bluish, or brownish reflections on the gauge or water.
            - Treat light blue, teal, or cyan hues below WHITE as GREEN unless the actual BLUE plate position (third) is clearly visible above water.
            - Ignore reflections on the water surface that are not physically on the gauge structure.

            4. Color fallback rules:
            - If you see the WHITE plate and the next visible color appears bluish, default to GREEN (second plate) unless the third BLUE plate is fully visible above water.
            - Only classify BLUE when you can clearly see the third plate section (below the green one) above the waterline.
            - If the top of the gauge (WHITE) is visible and no lower plates are visible, classify as WHITE.
            - If you see RED along with BLUE, GREEN, and WHITE visible above water, classify as RED (critical).

            5. Faded or mixed colors:
            - Slightly faded or dirty colors should still be classified based on their relative position rather than hue intensity.
            - When unsure, use the known fixed order (WHITE → GREEN → BLUE → RED) to reason spatially.
            
            Recommendation and observation rules based on ALL visible colors (Top → Bottom):
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

            If colors are unclear due to lighting or reflection, always default to the highest plausible water level (e.g., if unsure between green and blue, choose green)
            
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

def get_graph_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """
    Obtain an app-only Microsoft Graph token from the tenant-specific v2.0 endpoint
    """
    if not all([tenant_id, client_id, client_secret]):
        raise ValueError("Missing tenant_id/client_id/client_secret for Graph token acquisition")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default offline_access",
        "grant_type": "client_credentials",
    }

    resp = requests.post(token_url, data=data)
    try:
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Token request failed: {e}; status: {getattr(resp,'status_code',None)}; body: {resp.text}")

    token_json = resp.json()
    access_token = token_json.get("access_token")
    if not access_token:
        raise RuntimeError(f"No access token in token response: {token_json}")
    return access_token
                                            
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
    # send_sms_recommendations(recommendation_data)

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
 
def normalize_water_tones(image_file, reduce_factor=0.45):
    """
    Desaturate water-like hues (blue/green) to reduce water reflections and
    make the gauge colors more prominent for downstream AI processing
    """
    try:
        # Accept either a BytesIO/file-like or PIL Image
        if isinstance(image_file, (BytesIO,)):
            image_file.seek(0)
            pil = Image.open(image_file).convert('RGB')
        elif hasattr(image_file, 'read'):
            image_file.seek(0)
            pil = Image.open(image_file).convert('RGB')
        elif isinstance(image_file, Image.Image):
            pil = image_file.convert('RGB')
        else:
            # try to construct from bytes
            pil = Image.open(BytesIO(image_file)).convert('RGB')

        arr = np.array(pil)
        # convert RGB to BGR for OpenCV
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

        h = hsv[:, :, 0]
        s = hsv[:, :, 1]
        v = hsv[:, :, 2]

        # OpenCV hue range: 0-179
        # Water-like blue range and green range heuristics
        blue_mask = (h >= 90) & (h <= 140)
        green_mask = (h >= 35) & (h <= 85)

        # Combine masks and require some minimum brightness to avoid dark regions
        bright_mask = v >= 30
        mask = (blue_mask | green_mask) & bright_mask

        # Apply saturation reduction on masked pixels
        s_new = s.astype(np.float32)
        s_new[mask] = s_new[mask] * float(reduce_factor)
        s_new = np.clip(s_new, 0, 255).astype(np.uint8)
        hsv[:, :, 1] = s_new

        # Convert back to RGB
        bgr2 = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        rgb2 = cv2.cvtColor(bgr2, cv2.COLOR_BGR2RGB)
        pil_out = Image.fromarray(rgb2)
        out = BytesIO()
        pil_out.save(out, format='PNG')
        out.seek(0)
        return out
    except Exception as e:
        print(f"Color normalization failed: {e}")
        try:
            if hasattr(image_file, 'read'):
                image_file.seek(0)
                return BytesIO(image_file.read())
            elif isinstance(image_file, Image.Image):
                out = BytesIO()
                image_file.save(out, format='PNG')
                out.seek(0)
                return out
        except Exception:
            return image_file
        
def compare_images(prompt, image_1):
    resized_image = resize_image(image_1)
    try:
        normalize_flag = os.getenv('COLOR_NORMALIZATION', 'true').lower() in ['1', 'true', 'yes', 'on']
    except Exception:
        normalize_flag = True

    if normalize_flag:
        try:
            normalized = normalize_water_tones(resized_image)
            data_url = change_image_format(normalized)
        except Exception as e:
            print(f"Normalization failed, falling back: {e}")
            data_url = change_image_format(resized_image)
    else:
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