@echo off

cd D:\PromusProg\bibbi-aut

echo Updating WebDewey
call .venv\Scripts\console.cmd update_webdewey || goto :error

echo Exporting authorities
call .venv\Scripts\console.cmd authorities || goto :error

echo Extracting catalog
call .venv\Scripts\console.cmd catalog || goto :error

echo Uploading
call .venv\Scripts\console.cmd upload || goto :error

goto :finito

:error
echo Export failed with error #%errorlevel%.
exit /b %errorlevel%

:finito
echo Export completed successfully!
