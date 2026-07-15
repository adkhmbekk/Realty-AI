# Сборка нативного приложения (Android) — Realty AI

Веб-приложение (тот же React, что и Telegram Mini App) заворачивается в Capacitor и
собирается в APK/AAB. Telegram-сборка при этом не меняется (обычный `vite build`).

## 0. Предпосылки (проверить ОДИН раз)

- **Android Studio** установлен, встроенный JDK (JBR 21) — есть.
- **Android SDK** здоров (частая беда — недокачанный SDK). Через **SDK Manager**:
  - SDK Platforms: **Android 15 (API 35)** — полностью (должен появиться `platforms/android-35/android.jar`).
  - SDK Tools: **Platform-Tools** (adb), **Command-line Tools (latest)**, **Build-Tools**, **Emulator**.
- Переменная окружения **`ANDROID_HOME`** = `C:\Users\<user>\AppData\Local\Android\Sdk`
  (или файл `android/local.properties` с `sdk.dir=...` — Capacitor создаёт его сам при `cap sync`).

Проверка здоровья SDK (PowerShell):
```powershell
$sdk="$env:LOCALAPPDATA\Android\Sdk"
Test-Path "$sdk\platforms\android-35\android.jar"   # должно быть True
Test-Path "$sdk\platform-tools\adb.exe"             # должно быть True
```

## 1. Собрать веб-часть с адресом backend и OAuth-ключами

Адрес backend и Google-ключи вшиваются в сборку через env (Vite):
```powershell
$env:VITE_API_BASE="https://<твой-cloudflare-домен>"      # публичный backend (Фаза 4)
$env:VITE_GOOGLE_WEB_CLIENT_ID="<web client id>.apps.googleusercontent.com"
$env:VITE_GOOGLE_ANDROID_CLIENT_ID="<android client id>.apps.googleusercontent.com"
npm install
npm run build            # → dist/  (webDir для Capacitor)
```

## 2. Синхронизировать в нативный проект

```powershell
npx cap sync android     # копирует dist/ в android/ и обновляет плагины
```
(Первый раз, если папки android/ ещё нет: `npx cap add android`.)

## 3. Собрать APK

Вариант А — Android Studio (проще):
```powershell
npx cap open android     # откроет проект в Android Studio → Run ▶ или Build → Build APK(s)
```
Вариант Б — командой (Gradle wrapper):
```powershell
cd android
./gradlew assembleDebug  # APK: android/app/build/outputs/apk/debug/app-debug.apk
```

## 4. Установить на телефон

- Телефон в режиме разработчика + USB-отладка, подключить кабелем.
- `adb install -r android/app/build/outputs/apk/debug/app-debug.apk`

## 5. Настройка Google/Apple входа (обязательно для реального входа)

**Google (Android):**
- В Google Cloud Console создать OAuth client типа **Android**: package name `com.realtyai.app`
  + SHA-1 отпечаток debug-ключа:
  ```powershell
  keytool -list -v -keystore "$env:USERPROFILE\.android\debug.keystore" -alias androiddebugkey -storepass android -keypass android
  ```
  (для релиза — SHA-1 релизного keystore).
- Создать также client типа **Web** — его id идёт в `VITE_GOOGLE_WEB_CLIENT_ID` и в backend
  (`GOOGLE_WEB_CLIENT_ID`), т.к. Google возвращает id_token с `aud` = web client id.
- Backend должен знать эти же id (env `GOOGLE_ANDROID_CLIENT_ID`, `GOOGLE_WEB_CLIENT_ID`) —
  он по ним проверяет `aud` токена.

**Apple:** требует Apple Developer ($99/год) и Mac для iOS-сборки — отдельным этапом.

## Примечания
- `appId`: `com.realtyai.app`, `appName`: `Realty AI`, `webDir`: `dist` (см. `capacitor.config.ts`).
- CORS на backend уже разрешает `capacitor://localhost` / `https://localhost` (Фаза 1).
- Папки `android/` (и позже `ios/`) на Telegram-сборку не влияют.
