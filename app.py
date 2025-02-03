"""Streamlit entry point for the Touch 2025 RAD demo."""

import streamlit as st
from touche_rad.streamlit import Chat
import chromadb

chroma_client = chroma_client = chromadb.PersistentClient(path="chroma_db")

st.title("Touche 2025 RAD Demo")
st.markdown("""
This a demo of the Retrieval Augmented Dabate (RAD) system build by DS@GT CLEF Touche.
""")
Chat(chroma_client).render()
