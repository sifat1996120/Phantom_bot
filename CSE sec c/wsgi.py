import os
import sys

# Add your project directory to the path
project_dir = '/home/biittosaha/pikachu'
if project_dir not in sys.path:
    sys.path.append(project_dir)

# Import from main.py
from main import flask_app as application  # WSGI requires 'application'

# Set webhook if needed
TOKEN = "7925285512:AAG1R_MEsyxCqbC_0zQJSXwPJXcb-ATc8To"
if TOKEN:
    application.config['TELEGRAM_TOKEN'] = TOKEN