import streamlit as st
from datetime import datetime
import uuid


class Chat:
    def __init__(self, chroma_client):
        if "messages" not in st.session_state:
            st.session_state.messages = []
        if "conversation_id" not in st.session_state:
            st.session_state.conversation_id = str(uuid.uuid4())

        self.chroma_client = chroma_client
        self.session_id = (
            st.runtime.scriptrunner.script_run_context.get_script_run_ctx().session_id
        )
        # create or get collection
        self.collection = self.chroma_client.get_or_create_collection(
            name="conversations", metadata={"description": "Stored chat conversations"}
        )

    def _save_to_chroma(self, message):
        self.collection.add(
            documents=[message["content"]],
            metadatas=[
                {
                    "role": message["role"],
                    "conversation_id": st.session_state.conversation_id,
                    "session_id": self.session_id,
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            ids=[str(uuid.uuid4())],
        )

    def _handle_user(self, content):
        message = {
            "role": "user",
            "content": content,
        }
        st.session_state.messages.append(message)
        self._save_to_chroma(message)

    def _handle_assistant(self, content):
        message = {
            "role": "assistant",
            "content": f'You said "{content}"',
        }
        st.session_state.messages.append(message)
        self._save_to_chroma(message)

    def _display_messages(self):
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    def render(self):
        if content := st.chat_input("Ask me something."):
            self._handle_user(content)
            self._handle_assistant(content)
        self._display_messages()
