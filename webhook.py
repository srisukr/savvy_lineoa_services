import os
import hmac
import hashlib
import base64
import requests
import time
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
ADMIN_ID = os.environ.get("ADMIN_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
LINESHOP_KEY = os.environ.get("LINESHOP_KEY")
engine = create_engine(DATABASE_URL)
Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False)
    text = Column(Text, nullable=False)
    user_id = Column(String, nullable=False)

class AdminMessage(Base):
    __tablename__ = "admin_messages"
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False)
    text = Column(Text, nullable=False)
    user_id = Column(String, nullable=False)

class UserProfile(Base):
    __tablename__ = "user_profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, unique=True, nullable=False)
    display_name = Column(String)

class ChatGPTLog(Base):
    __tablename__ = "chatgpt_logs"
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False)
    user_id = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=False)

class LineMyShopOrder(Base):
    __tablename__ = "line_myshop_orders"
    id = Column(Integer, primary_key=True)
    order_number = Column(String, nullable=False)
    order_status = Column(String)
    event_name = Column(String)
    event_timestamp = Column(String)
    payment_method = Column(String)
    payment_status = Column(String)
    recipient_name = Column(String)
    phone_number = Column(String)
    address = Column(String)
    shipment_company_name = Column(String)
    tracking_number = Column(String)
    subtotal_price = Column(Float)
    total_price = Column(Float)
    shipment_price = Column(Float)
    is_cod = Column(Boolean)
    is_gift = Column(Boolean)
    raw_data = Column(Text)
    date = Column(DateTime, default=datetime.utcnow)
    items = relationship("LineMyShopOrderItem", back_populates="order")

class LineMyShopOrderItem(Base):
    __tablename__ = "line_myshop_order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('line_myshop_orders.id'))
    name = Column(String)
    sku = Column(String)
    quantity = Column(Integer)
    price = Column(Float)
    discounted_price = Column(Float)
    barcode = Column(String)
    weight = Column(Float)
    image_url = Column(String)
    raw_data = Column(Text)
    order = relationship("LineMyShopOrder", back_populates="items")

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

def reply_to_line_user(user_id, text):
    print("🤖 Replying to user via LINE")
    headers = {
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }
    response = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=headers,
        json=payload
    )
    print(f"Reply status: {response.status_code} {response.text}")

def get_user_name(user_id):
    try:
        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
        }
        response = requests.get(f"https://api.line.me/v2/bot/profile/{user_id}", headers=headers)
        if response.status_code == 200:
            profile = response.json()
            return profile.get("displayName")
        else:
            print(f"⚠️ Failed to fetch user profile: {response.status_code} {response.text}")
    except Exception as e:
        print("⚠️ Exception in get_user_name:", e)
    return None

def call_chatgpt(prompt):
    print("🤖 Calling ChatGPT API")
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-3.5-turbo",
        "temperature": 0.7,
        "max_tokens": 300,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant who answers concisely and clearly."},
            {"role": "user", "content": prompt}
        ]
    }
    retries = 3
    backoff = 1

    for attempt in range(retries):
        try:
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            if response.status_code == 200:
                reply = response.json()["choices"][0]["message"]["content"].strip()
                return reply
            else:
                print(f"⚠️ ChatGPT API error ({response.status_code}): {response.text}")
        except Exception as e:
            print(f"⚠️ Exception in call_chatgpt (attempt {attempt + 1}):", e)

        time.sleep(backoff)
        backoff *= 2

    return "I'm sorry, I couldn't generate a response."

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

                    if user_id == ADMIN_ID:
                        admin_message = AdminMessage(date=date, text=text, user_id=user_id)
                        session.add(admin_message)
                        session.commit()
                        continue

                    # if user_id == FORWARD_USER_ID:
#     reply = call_chatgpt(text)
#     reply_to_line_user(user_id, reply)
#     chat_log = ChatGPTLog(date=date, user_id=user_id, prompt=text, response=reply)
#     session.add(chat_log)
#     session.commit()
                        continue

                    message = Message(date=date, text=text, user_id=user_id)
                    session.add(message)

                    existing_user = session.query(UserProfile).filter_by(user_id=user_id).first()
                    if not existing_user:
                        print(f"🔍 No profile found for {user_id}, trying to fetch...")
                        display_name = get_user_name(user_id)
                        print(f"📛 Fetched display name: {display_name}")
                        if display_name:
                            print(f"👤 Saving user profile: {display_name}")
                            new_user = UserProfile(user_id=user_id, display_name=display_name)
                            session.add(new_user)

                    session.commit()

                    if FORWARD_USER_ID:
                        print(f"🟢 FORWARD_USER_ID found: {FORWARD_USER_ID}")
                        forward_message_to_user(FORWARD_USER_ID, text)

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print("❌ Error:", e)
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

def is_valid_myshop_signature(req):
    signature = req.headers.get("x-myshop-signature")
    body = req.get_data(as_text=True)
    expected_signature = hmac.new(
        LINESHOP_KEY.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)

@app.route('/sassy-line-myshop-webhook', methods=['POST'])
def sassy_line_myshop_webhook():
    if not is_valid_myshop_signature(request):
        print("❌ Invalid LINE MyShop signature")
        abort(403)

    try:
        data = request.get_json()
        print("📦 LINE MyShop Payload:", data)

        order = LineMyShopOrder(
            order_number = data.get("orderNumber"),
            order_status = data.get("orderStatus"),
            event_name = data.get("event", {}).get("name"),
            event_timestamp = data.get("event", {}).get("timestamp"),
            payment_method = data.get("paymentMethod"),
            payment_status = data.get("paymentStatus"),
            recipient_name = data.get("shippingAddress", {}).get("recipientName"),
            phone_number = data.get("shippingAddress", {}).get("phoneNumber"),
            address = data.get("shippingAddress", {}).get("address"),
            shipment_company_name = data.get("shipmentDetail", {}).get("shipmentCompanyNameTh"),
            tracking_number = data.get("shipmentDetail", {}).get("trackingNumber"),
            subtotal_price = data.get("subtotalPrice", 0),
            total_price = data.get("totalPrice", 0),
            shipment_price = data.get("shipmentPrice", 0),
            is_cod = data.get("shipmentDetail", {}).get("isCod", False),
            is_gift = data.get("isGift", False),
            raw_data = str(data)
        )

        session.add(order)
        session.flush()  # get order.id for item linkage

        for item in data.get("orderItems", []):
            order_item = LineMyShopOrderItem(
                order_id = order.id,
                name = item.get("name"),
                sku = item.get("sku"),
                quantity = item.get("quantity", 0),
                price = item.get("price", 0),
                discounted_price = item.get("discountedPrice", 0),
                barcode = item.get("barcode"),
                weight = item.get("weight", 0),
                image_url = item.get("imageURL"),
                raw_data = str(item)
            )
            session.add(order_item)

        session.commit()
        return jsonify({"status": "received"}), 200

    except Exception as e:
        print("❌ Error in LINE MyShop webhook:", e)
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


    
if __name__ == '__main__':
    app.run(debug=True)
