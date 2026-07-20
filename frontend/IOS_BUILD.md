# Realty AI — iOS (Capacitor) build & release

iOS-проект уже **сгенерирован и настроен на Windows** (`frontend/ios/`, закоммичен в
`feature/native-auth`). Тот же веб-фронт, что и Android/Telegram — общий бэкенд.
Собрать `.ipa`, подписать и опубликовать можно **только на macOS с Xcode** — всё
остальное готово. Ниже — что сделано и точные шаги на Mac.

> **Важно про Capacitor 8:** зависимости плагинов идут через **Swift Package Manager
> (`ios/App/CapApp-SPM/Package.swift`)**, а НЕ CocoaPods. Никакого `pod install` —
> Xcode сам подтянет пакеты при открытии проекта.

---

## Что уже сделано (Windows, в репозитории)

- `@capacitor/ios@8` установлен; `npx cap add ios` создал Xcode-проект.
- `appId = com.realtyai.app`, `appName = "Realty AI"` (тот же bundle id, что и Android —
  единый бренд). Deployment target **iOS 15.0**.
- **Info.plist** (`ios/App/App/Info.plist`): добавлены строки прав
  `NSCameraUsageDescription` + `NSPhotoLibraryUsageDescription` — агент прикрепляет
  фото объекта через `<input type="file">`, в WKWebView это открывает системный пикер
  (без строк App Store отклоняет).
- Все 6 плагинов подхватились для iOS, включая:
  - `@aparajita/capacitor-secure-storage` → на iOS это **Keychain** (токены сессии
    шифруются автоматически, код `session.ts` уже кросс-платформенный, менять нечего).
  - `@capacitor/app`, `haptics`, `status-bar`, `preferences`, `@capgo/capacitor-social-login`.
- `ios/.gitignore` (от Capacitor) исключает `App/build`, `App/App/public` (веб-ассеты),
  `DerivedData`, `xcuserdata` — в гите только исходники.

## Вход в приложении на iOS — уже работает так же, как на Android

- **Telegram-вход:** `window.open(deep_link, "_system")` открывает t.me, дальше
  приложение **поллит** `/auth/telegram/poll`. Никакого URL-scheme callback / deep-link
  возврата не нужно — просто проверь, что открывается Safari→Telegram и возврат ловится
  поллингом.
- **Вход по номеру (SMS):** полностью на бэкенде, кросс-платформенный. Заработает, когда
  включим Eskiz (нужны креды — бэклог). UI-кнопка уже есть.
- **Google/Apple:** из UII убраны (оставили Telegram + номер). Поэтому для App Store
  **не** триггерится обязательный «Sign in with Apple» (правило 4.8 — оно про сторонние
  соц-входы). Если вернём Google/Apple — см. раздел «Опционально» ниже.

---

## Шаги на MacBook (по порядку)

### 0. Окружение
```bash
# Xcode из App Store (последний), затем командные инструменты:
xcode-select --install
# Клонируем репозиторий, ветка с нативом:
git clone <repo> && cd Realty-AI && git checkout feature/native-auth
cd frontend
npm install
```

### 1. Собрать веб и синхронизировать в iOS
> `VITE_API_BASE` вшивается в бандл на этапе `npm run build`. Убедись, что перед сборкой
> в окружении/`.env` стоит **прод-адрес бэкенда** (тот же, что для Android — Tailscale
> funnel `https://pc1.tailcdc07f.ts.net` или актуальный прод-URL).
```bash
npm run build
npx cap sync ios      # копирует dist → ios, обновляет плагины (SPM)
npx cap open ios      # откроет ios/App/App.xcodeproj в Xcode
```

### 2. Подпись (Signing)
В Xcode: таргет **App** → вкладка **Signing & Capabilities**:
- Включить **Automatically manage signing**.
- Выбрать свою **Team** (нужен аккаунт Apple Developer Program, $99/год).
- **Bundle Identifier** уже `com.realtyai.app` — зарегистрируй этот id в
  developer.apple.com → Identifiers (или Xcode предложит создать автоматически).

### 3. Версия
В таргете (или `project.pbxproj`): `MARKETING_VERSION` (сейчас `1.0`) и
`CURRENT_PROJECT_VERSION` (build number, сейчас `1`). Для каждой загрузки в App Store
Connect build number должен расти.

### 4. Иконка приложения (ЕДИНСТВЕННЫЙ недостающий ассет)
Сейчас в проекте **дефолтная иконка Capacitor** — на Windows не было исходника
достаточного размера (у Android-иконки максимум 192px, для iOS нужен 1024×1024).
Когда будет фирменный **1024×1024 PNG** (исходник логотипа Realty AI):
```bash
# положить его в frontend/resources/icon.png (и опционально resources/splash.png 2732×2732)
npm i -D @capacitor/assets
npx capacitor-assets generate --ios   # сгенерит весь набор иконок + splash
npx cap sync ios
```
(Эту команду можно выполнить и на Windows заранее — она кросс-платформенная.)

### 5. Запуск и публикация
- **Симулятор/устройство:** выбрать схему **App**, ⌘R. Для реального iPhone — устройство
  должно быть добавлено в профиль (при Automatic signing Xcode сделает сам).
- **App Store:** Product → **Archive** → Distribute App → App Store Connect. Предварительно
  в App Store Connect создать запись приложения (bundle id `com.realtyai.app`), заполнить
  метаданные, приватность (собираем: имя, номер телефона), скриншоты, и дать ревьюерам
  тестовый доступ (демо-аккаунт или инструкцию для входа по номеру/Telegram).

---

## Опционально — если позже вернём Google/Apple-вход на iOS

`nativeAuth.ts` уже умеет инициализировать `@capgo/capacitor-social-login`; на iOS нужно:
- **Apple:** таргет → Signing & Capabilities → **+ Capability → Sign in with Apple**.
  Задать `VITE_APPLE_CLIENT_ID` (Services ID) при сборке. Apple-вход обязателен, если на
  экране есть другие соц-входы (Google/FB) — правило App Store 4.8.
- **Google:** создать **iOS OAuth client id** в Google Cloud (бэклог: `iOSServerClientId`),
  прописать `VITE_GOOGLE_IOS_CLIENT_ID`, и добавить в Info.plist URL-scheme = reversed
  client id (`com.googleusercontent.apps.<...>`) в `CFBundleURLTypes`.

## Частые грабли
- **«No such module 'Capacitor'»** при первой сборке → Xcode ещё резолвит Swift-пакеты;
  подожди индексацию (File → Packages → Resolve Package Versions), затем собери заново.
- **Белый экран** → не сделан `npm run build` перед `cap sync`, или `VITE_API_BASE`
  пустой/localhost. Проверь `ios/App/App/public/index.html` существует и `capacitor.config.json`
  содержит правильный `server`/`webDir`.
- **CORS/сеть** → бэкенд уже разрешает origin `capacitor://localhost` (Фаза 1). Если новый
  прод-домен — добавить его в CORS на бэке.
- **Фото не выбираются** → проверь, что строки `NS*UsageDescription` на месте (они есть).
