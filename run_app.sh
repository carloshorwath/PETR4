#!/bin/bash
echo "Installing dependencies..."
pip install -r requirements.txt

echo "Running Application..."
streamlit run src/app.py
