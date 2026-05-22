@echo off
:: run_pipeline.bat — Windows Task Scheduler Launcher Wrapper
:: Anchors the script path and executes the pipeline in the Miniconda environment.

:: Change directory to where this batch file lives (the project root)
cd /d "%~dp0"

echo [TASK SCHEDULER] Starting Mutual Fund Pipeline at %DATE% %TIME%...

:: Check if Miniconda environment exists and activate it
set CONDA_ACTIVATE="C:\Users\krish\miniconda3\Scripts\activate.bat"
set CONDA_ENV="C:\Users\krish\miniconda3\envs\mutual_fund_dashboard"

if not exist %CONDA_ACTIVATE% (
    echo [ERROR] conda activate.bat not found at %CONDA_ACTIVATE%
    echo [ERROR] Please verify your Miniconda3 installation path.
    exit /b 1
)

if not exist %CONDA_ENV% (
    echo [ERROR] conda env not found at %CONDA_ENV%
    echo [ERROR] Please run 'conda create -n mutual_fund_dashboard python=3.11' first.
    exit /b 1
)

:: Activate the environment and run the pipeline orchestrator
echo [TASK SCHEDULER] Activating conda environment: mutual_fund_dashboard
call %CONDA_ACTIVATE% %CONDA_ENV%

echo [TASK SCHEDULER] Executing run_pipeline.py...
python run_pipeline.py %*

set EXIT_CODE=%ERRORLEVEL%
echo [TASK SCHEDULER] Pipeline execution finished with code %EXIT_CODE% at %DATE% %TIME%.
exit /b %EXIT_CODE%
