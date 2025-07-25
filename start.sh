#!/bin/bash

# Activate virtual environment
source venv/bin/activate

# Initialize database if it doesn't exist
python init_db.py

# Start the bot
python bot.py 