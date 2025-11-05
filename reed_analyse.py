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
# from dotenv import load_dotenv
# load_dotenv()
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
            - If you see ONLY the WHITE plate is visible above the water, classify as WHITE
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
                                      
def get_azure_token():
    tenant_id = os.getenv("SP_TENANT_ID")
    client_id = os.getenv("SP_CLIENT_ID")
    client_secret = os.getenv("SP_CLIENT_SECRET")
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    resp = requests.post(token_url, data=data)
    resp.raise_for_status()
    token_json = resp.json()
    access_token = token_json.get("access_token")
    if not access_token:
        raise RuntimeError(f"No access token: {token_json}")
    return access_token

def get_site_id(token):
    url = "https://graph.microsoft.com/v1.0/sites/victoryfarmsltd.sharepoint.com:/sites/TechnologyandInnovation"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    site = resp.json()
    return site["id"]

def get_drive_id(site_id, token):
    # Use site name instead of ID
    url = f"https://graph.microsoft.com/v1.0/sites/TechnologyandInnovation/drive"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    drive = resp.json()
    return drive["id"]

def get_item_id(drive_id, path, token):
    # Do not encode spaces, let requests handle it
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{path}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    item = resp.json()
    return item["id"]

def get_table_id(drive_id, item_id, worksheet_name, table_name, token):
    # Get worksheet id
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{worksheet_name}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    worksheet = resp.json()
    worksheet_id = worksheet["id"]
    # Get tables in worksheet
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{worksheet_id}/tables"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    tables = resp.json().get("value", [])
    for table in tables:
        if table["name"] == table_name:
            return table["id"]
    raise ValueError(f"Table '{table_name}' not found in worksheet '{worksheet_name}'")

def add_rows_to_table(drive_id, item_id, table_id, rows, token):
    # Ensure rows match the table's column count (pad with blanks if needed)
    def _get_table_column_count():
        url_cols = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/tables/{table_id}/columns?$select=index"
        headers_cols = {"Authorization": f"Bearer {token}"}
        r_cols = requests.get(url_cols, headers=headers_cols)
        r_cols.raise_for_status()
        return len(r_cols.json().get("value", []))

    col_count = _get_table_column_count()
    padded_rows = [row + [""] * max(0, col_count - len(row)) for row in rows]

    # Create session
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/createSession"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(url, json={"persistChanges": True}, headers=headers)
    resp.raise_for_status()
    session = resp.json()
    session_id = session["id"]
    # Add rows
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/tables/{table_id}/rows"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "workbook-session-id": session_id}
    body = {"values": padded_rows}
    resp = requests.post(url, json=body, headers=headers)
    resp.raise_for_status()
    # Close session
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/closeSession"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "workbook-session-id": session_id}
    resp = requests.post(url, headers=headers)
    resp.raise_for_status()

def to_sheet(pond_identity, observation, recommendation, pond_category):
    kenya_tz = pytz.timezone('Africa/Nairobi')
    current_datetime = datetime.now(kenya_tz)
    formatted_datetime = "VF-" + current_datetime.strftime("%Y-%m-%d-%H:%M")

    token = get_azure_token()
    sharing_url = "https://victoryfarmsltd.sharepoint.com/:x:/r/sites/TechnologyandInnovation/Shared%20Documents/Drone%20Department/Drone%20Photos/POND%20WATER%20LEVEL%20MANAGEMENT/Pond%20Water%20Analysis%20Project1.xlsx?d=w9dfe35bfc2854d53a2512c15a36ab13d&csf=1&web=1&e=A0OGHh"
    drive_id, item_id = get_drive_and_item_from_sharing_url(sharing_url, token)
    table_id = get_table_id(drive_id, item_id, "Input", "Input", token)

    row = [
        formatted_datetime,   # Date
        pond_identity,        # Pond Name
        observation,          # Observation
        recommendation,       # Recommendation
        pond_category         # Pond Category
    ]


    add_rows_to_table(drive_id, item_id, table_id, [row], token)
    return True
    
def to_sheet_batch(recommendation_data):
    kenya_tz = pytz.timezone('Africa/Nairobi')
    current_datetime = datetime.now(kenya_tz)
    formatted_datetime = "VF-" + current_datetime.strftime("%Y-%m-%d-%H:%M")

    token = get_azure_token()
    sharing_url = "https://victoryfarmsltd.sharepoint.com/:x:/r/sites/TechnologyandInnovation/Shared%20Documents/Drone%20Department/Drone%20Photos/POND%20WATER%20LEVEL%20MANAGEMENT/Pond%20Water%20Analysis%20Project1.xlsx?d=w9dfe35bfc2854d53a2512c15a36ab13d&csf=1&web=1&e=A0OGHh"
    drive_id, item_id = get_drive_and_item_from_sharing_url(sharing_url, token)
    table_id = get_table_id(drive_id, item_id, "Input", "Input", token)

    rows = []
    for recommendation in recommendation_data:
        row = [
            formatted_datetime,                          # Date
            recommendation.get('Pond Identifier', ''),   # Pond Name
            recommendation.get('observations', ''),      # Observation
            recommendation.get('Recommendation', ''),    # Recommendation
            recommendation.get('Pond Category', '')      # Pond Category
        ]
        rows.append(row)

    add_rows_to_table(drive_id, item_id, table_id, rows, token)
    return True

    # --- Send email after writing to Excel ---
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

def sharing_url_to_share_id(sharing_url):
    url_bytes = sharing_url.encode("utf-8")
    b64_url = base64.urlsafe_b64encode(url_bytes).decode("utf-8").rstrip("=")
    return f"u!{b64_url}"

def get_drive_and_item_from_sharing_url(sharing_url, token):
    share_id = sharing_url_to_share_id(sharing_url)
    url = f"https://graph.microsoft.com/v1.0/shares/{share_id}/driveItem"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    item = resp.json()
    drive_id = item["parentReference"]["driveId"]
    item_id = item["id"]
    return drive_id, item_id