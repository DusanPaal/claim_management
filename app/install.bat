@ECHO OFF

ECHO === Claim Management Services Setup ver. 1.2.20221017 ===
set /P choice="Do you wish to install the component? (Y/N): "

IF NOT %choice%==Y IF NOT %choice%==y (
  pause>nul|set/p=Invalid parameter entered. Press any key to exit setup ...
  EXIT /b 0
)

ECHO Installing application...
ECHO Detecting python virtual environment ...

IF EXIST "env/Scripts/python.exe" (

  SETLOCAL enabledelayedexpansion
  SET/P choice="A python virtual environment already exists. Do you wish to reinstall? (Y/N): "
    
  IF NOT !choice!==Y IF NOT !choice!==y (
    pause>nul|set/p=Invalid parameter entered. Press any key to exit setup ...
    EXIT /b 0
  )

  ECHO Removing existing virtual environment ...
  RD /s /q env
  ENDLOCAL

) ELSE (
  ECHO Python virtual environment needs to be installed.
)

SET /P pypath="Enter path to python home executable: "

if NOT EXIST %pypath% (
  pause>nul|set/p=Invaid path entered! Press any key to exit setup ...
  EXIT /b 0
)

ECHO Creating virtual environment ...
%pypath% -m venv env

ECHO Updating virtual environment ...
env\Scripts\python.exe -m pip install --upgrade pip
env\Scripts\python.exe -m pip install --upgrade setuptools
ECHO:

ECHO Installing packages ...
env\Scripts\python.exe -m pip install -r requirements.txt

pause>nul|set/p=Installation completed. Press any key to exit setup ...