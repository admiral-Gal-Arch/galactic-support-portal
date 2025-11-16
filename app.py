# support_portal.py

import streamlit as st
import pymongo
import pandas as pd
import streamlit_authenticator as stauth
from pymongo.server_api import ServerApi
from datetime import datetime
import os 

# --- Page Configuration ---
st.set_page_config(
    page_title="Support Terminal",
    page_icon="📡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --- Custom CSS ---
def load_css():
    st.markdown(
        """
        <style>
        /* (CSS styles are unchanged) */
        html, body, [class*="st-"] { background-color: #0F1116; color: #EAEAEA; }
        h1 { color: #00FFFF; text-shadow: 0 0 8px #00FFFF; font-family: 'Orbitron', sans-serif; }
        h2, h3 { color: #00FFFF; }
        .stButton > button { border: 2px solid #00FFFF; background-color: transparent; color: #00FFFF; border-radius: 8px; transition: all 0.3s; }
        .stButton > button:hover { background-color: #00FFFF; color: #0F1116; box-shadow: 0 0 10px #00FFFF; }
        .stForm [data-testid="stButton"] button { background-color: #00FFFF; color: #0F1116; border: none; font-weight: bold; }
        .stForm [data-testid="stButton"] button:hover { background-color: #EAEAEA; color: #0F1116; box-shadow: 0 0 10px #00FFFF; }
        .stTabs [data-testid="stTab"] { background-color: transparent; border: 1px solid #00B4B4; }
        .stTabs [data-testid="stTab"][aria-selected="true"] { background-color: #00B4B4; color: white; border-bottom: none; }
        .stTextInput > div > div > input, .stTextArea > div > textarea { background-color: #1C1E25; color: #EAEAEA; border: 1px solid #00B4B4; }
        .st-expander { border: 1px solid #00B4B4; border-radius: 8px; background-color: #1C1E25; }
        .st-expander summary { font-weight: bold; color: #00FFFF; }
        </style>
        """,
        unsafe_allow_html=True,
    )

load_css()

# --- 1. MongoDB Connection ---

@st.cache_resource
def init_connection():
    try:
        uri = os.environ.get("MONGO_URI")
        if not uri:
            st.error("MONGO_URI environment variable not set.")
            return None
            
        client = pymongo.MongoClient(uri, server_api=ServerApi('1'))
        client.admin.command('ping')
        return client
    except Exception as e:
        st.error(f"Failed to connect to Archive. Please try again later. {e}")
        return None

client = init_connection()

if client is None:
    st.stop()

@st.cache_resource
def get_database(db_name):
    return client[db_name]

@st.cache_resource
def get_collection(db_name, collection_name):
    db = get_database(db_name)
    return db[collection_name]

# --- Get collections ---
public_users_collection = get_collection("support_center", "public_users")
tickets_collection = get_collection("support_center", "tickets")


# --- 2. User Authentication ---

@st.cache_data(ttl=600)
def fetch_all_users():
    try:
        return list(public_users_collection.find({}, {"_id": 0}))
    except Exception as e:
        st.error(f"Error connecting to user database: {e}")
        return []

users = fetch_all_users()

# --- THIS IS THE FIX ---
# Use .get() for safety. This will no longer crash.
credentials = {
    "usernames": {
        user.get("username"): {
            "name": user.get("name"),
            "email": user.get("email"),
            "password": user.get("password")
        }
        for user in users if user.get("username") # Also filter out bad/empty docs
    }
}
# --- END OF FIX ---

# --- Initialize the Authenticator ---
try:
    authenticator = stauth.Authenticate(
        credentials, # We pass the local dictionary here
        os.environ.get("USER_COOKIE_NAME"),
        os.environ.get("USER_COOKIE_KEY"),
        int(os.environ.get("USER_COOKIE_EXPIRY", 30))
    )
except Exception as e:
    st.error(f"Error initializing authenticator: {e}. Check cookie environment variables.")
    st.stop()
    

# --- 3. Login, Register, & Forgot Password Widgets ---

if "authentication_status" not in st.session_state:
    st.session_state.authentication_status = None

if st.session_state.authentication_status is None:
    st.title("Galactic Archives Support")
    st.header("Access Terminal")
    
    login_tab, register_tab = st.tabs(["[ Login ]", "[ Register ]"])

    with login_tab:
        name, authentication_status, username = authenticator.login() or (None, None, None)

    with register_tab:
        try:
            if authenticator.register_user():
                
                # Get the username from session_state (set by authenticator)
                username = st.session_state.username
                
                # Access the local 'credentials' dict, which was mutated
                # This dictionary now contains the new user's hashed password.
                new_user_data = credentials["usernames"][username]
                
                public_users_collection.insert_one(new_user_data)
                st.success('User registered successfully! Please go to the Login tab.')
                fetch_all_users.clear()
        except Exception as e:
            st.error(f"Error during registration: {e}")

# --- 4. Main Application (Logged-in View) ---
if st.session_state.authentication_status:
    name = st.session_state.name
    username = st.session_state.username

    st.sidebar.title(f"Welcome, *{name}*")
    authenticator.logout('Logout', 'sidebar')

    st.header("Support & Diagnostics Terminal")

    tab1, tab2 = st.tabs(["[ Submit New Transmission ]", "[ My Transmission Archive ]"])

    # --- TAB 1: Submit New Ticket ---
    with tab1:
        st.subheader("📡 Open a New Support Channel")
        
        with st.form("new_ticket_form", clear_on_submit=True):
            subject = st.text_input("Subject", placeholder="e.g., Hyperdrive Malfunction")
            category = st.selectbox(
                "System Category",
                ["Archive Access", "Starship Systems", "Account/Billing", "Data Anomaly", "Other"]
            )
            description = st.text_area("Full Description", height=150, placeholder="Please provide all relevant details...")
            
            submitted = st.form_submit_button("Transmit Request")

        if submitted:
            if not subject or not description:
                st.warning("Please fill out the Subject and Description fields.")
            else:
                try:
                    ticket_data = {
                        "user_email": username,
                        "subject": subject,
                        "category": category,
                        "description": description,
                        "status": "New",
                        "created_at": datetime.now(),
                        "assigned_to": None,
                        "internal_notes": ""
                    }
                    tickets_collection.insert_one(ticket_data)
                    st.success("Support request transmitted successfully! We will contact you at your registered email.")
                except Exception as e:
                    st.error(f"Transmission failed. Please try again. Error: {e}")

    # --- TAB 2: View My Tickets ---
    with tab2:
        st.subheader("📝 My Support History")
        
        try:
            user_tickets = list(tickets_collection.find(
                {"user_email": username},
                sort=[("created_at", pymongo.DESCENDING)]
            ))
            
            if not user_tickets:
                st.info("You have no support transmissions in the archive.")
            else:
                for ticket in user_tickets:
                    ticket_id = str(ticket["_id"])
                    
                    with st.expander(f"**{ticket.get('subject', 'No Subject')}** (Status: {ticket.get('status', 'N/A')})"):
                        st.markdown(f"**Submitted:** {ticket.get('created_at', 'N/A').strftime('%Y-%m-%d %H:%M')}")
                        st.markdown(f"**Category:** {ticket.get('category', 'N/A')}")
                        st.divider()
                        st.write("**Your Message:**")
                        st.info(ticket.get('description', ''))
                        
                        notes = ticket.get("internal_notes", "")
                        if notes.strip():
                             st.divider()
                             st.write("**Archive Staff Notes:**")
                             st.warning(notes)

        except Exception as e:
            st.error(f"Failed to retrieve ticket archive. Error: {e}")

# --- 5. Login-Failed Logic ---
elif st.session_state.authentication_status == False:
    st.error('Username/password is incorrect')
elif st.session_state.authentication_status == None:
    pass
