@echo off
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Dependencies installed!
echo.
echo Running Application...
streamlit run src/app.py
pause
