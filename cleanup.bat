@echo off
echo ========================================
echo Cleaning Up Project Structure
echo ========================================

echo.
echo Stopping any running Python processes...
timeout /t 2 /nobreak >nul

echo Deleting unnecessary files...
del /F /Q app_enhanced.py 2>nul
del /F /Q app_professional.py 2>nul
del /F /Q api_server.py 2>nul
del /F /Q api_server_simple.py 2>nul
del /F /Q LANGCHAIN_README.md 2>nul

echo Deleting cache and temp folders...
rmdir /S /Q __pycache__ 2>nul
rmdir /S /Q notebooks 2>nul

echo.
echo ========================================
echo Cleanup Complete!
echo ========================================
echo.
echo Final Structure:
echo   frontend/        - React UI
echo   backend/         - Flask API
echo   src/             - Python logic
echo   app.py           - Streamlit Original
echo   app_langchain.py - Streamlit LangChain
echo   setup_database.py - DB setup script
echo.
pause
