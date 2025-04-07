import os
import hmac
import hashlib
import base64
import requests
from flask import Flask, request, jsonify, abort
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import NoResultFound
from datetime import datetime
from dotenv import load_dotenv

# Load .env file in local development
load_dotenv()

# Flask App
app = Flask(__name__)

# DB Config
DATABASE_URL = os.environ.get("DATABASE_URL")
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
FORWARD_USER_ID = os.environ.get("FORWARD_USER_ID")
engine = create_engine(DATABASE_URL)
Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False)
    text = Column(Text, nullable=False)
    user_id = Column(String, nullable=False)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

def forward_message_to_user(user_id, text):
    print("🛫 Entered forward_message_to_user()")
    headers = {
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": f"[Forwarded] {text}"
            }
        ]
    }
    response = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=headers,
        json=payload
    )
    print(f"Forward status: {response.status_code} {response.text}")

def is_valid_signature(request):
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    hash = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).digest()
    computed_signature = base64.b64encode(hash).decode()
    return hmac.compare_digest(computed_signature, signature)

@app.route('/webhook', methods=['POST'])
def webhook():
    if not is_valid_signature(request):
        print("❌ Invalid signature: possible spoofed request")
        abort(403)

    try:
        data = request.get_json()
        print("📩 Raw Payload:", data)

        if "events" in data:
            for event in data["events"]:
                if event["type"] == "message" and event["message"]["type"] == "text":
                    user_id = event["source"]["userId"]
                    text = event["message"]["text"]
                    timestamp = int(event["timestamp"]) // 1000
                    date = datetime.fromtimestamp(timestamp)

                    print(f"💬 Received from {user_id}: {text}")

                    # Save message to DB
                    message = Message(date=date, text=text, user_id=user_id)
                    session.add(message)
                    session.commit()

                    # Forward message to admin (using env var FORWARD_USER_ID)
                    if FORWARD_USER_ID:
                        print(f"🟢 FORWARD_USER_ID found: {FORWARD_USER_ID}")
                        forward_message_to_user(FORWARD_USER_ID, text)

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print("❌ Error:", e)
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
