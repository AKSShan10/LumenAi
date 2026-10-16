"""Transcripts: the live transcript of the interview call.

Each browser sends its own microphone (WebSocket), speech-to-text turns it into sentences, and every finished
sentence is saved with the speaker and the time from the interview start. The sound itself is never stored.
"""
