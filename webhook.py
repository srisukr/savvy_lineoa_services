import os
from flask import Flask, request, jsonify
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import NoResultFound
from datetime import datetime
from dotenv import load_dotenv

# Load .env for local development
load_dotenv()

# Flask App
app = Flask(__name__)

# DB Config
DATABASE_URL = os.environ.get("DATABASE_URL")
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

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        print("==== RAW DATA RECEIVED ====")
        print(data)

        if "events" in data:
            print("==== EVENTS FOUND ====")
            for event in data["events"]:
                print("Processing event:", event)
                if event["type"] == "message" and "text" in event["message"]:
                    user_id = event["source"]["userId"]
                    text = event["message"]["text"]
                    timestamp = datetime.fromtimestamp(int(event["timestamp"]) // 1000)

                    message = Message(date=timestamp, text=text, user_id=user_id)
                    session.add(message)
                    session.commit()
                    print(f"Saved: {text} from {user_id}")

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print("Error:", e)
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
