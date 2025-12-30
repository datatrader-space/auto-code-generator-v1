@echo off
REM ================================
REM Quick Vue Setup (Windows BAT)
REM ================================

REM Go to frontend directory
cd frontend || exit /b

REM Create directories
mkdir src\views
mkdir src\services
mkdir src\router
mkdir src\components

REM ----------------
REM Create index.html
REM ----------------
(
echo ^<!DOCTYPE html^>
echo ^<html lang="en"^>
echo   ^<head^>
echo     ^<meta charset="UTF-8" /^>
echo     ^<meta name="viewport" content="width=device-width, initial-scale=1.0" /^>
echo     ^<title^>CRS Agent^</title^>
echo   ^</head^>
echo   ^<body^>
echo     ^<div id="app"^>^</div^>
echo     ^<script type="module" src="/src/main.js"^>^</script^>
echo   ^</body^>
echo ^</html^>
) > index.html

REM ----------------
REM Create vite.config.js
REM ----------------
(
echo import { defineConfig } from 'vite'
echo import vue from '@vitejs/plugin-vue'
echo.
echo export default defineConfig({
echo   plugins: [vue()],
echo   server: {
echo     port: 5173
echo   }
echo })
) > vite.config.js

REM ----------------
REM Create tailwind.config.js
REM ----------------
(
echo export default {
echo   content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
echo   theme: { extend: {} },
echo   plugins: [],
echo }
) > tailwind.config.js

REM ----------------
REM Create postcss.config.js
REM ----------------
(
echo export default {
echo   plugins: {
echo     tailwindcss: {},
echo     autoprefixer: {},
echo   },
echo }
) > postcss.config.js

REM ----------------
REM Create src/style.css
REM ----------------
(
echo @tailwind base;
echo @tailwind components;
echo @tailwind utilities;
) > src\style.css

echo.
echo ✅ Vue structure created!
echo Now copy the Vue component files from artifacts
