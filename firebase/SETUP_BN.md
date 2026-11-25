# SHUNCHi account setup (Firebase), ~10 minutes, free

Account sob kaj kore **Firebase** diye. Config na dile website/app/admin-e account button-i dekhabe na, kono kichu bhange na.

## 1. Project
1. https://console.firebase.google.com -> **Add project** -> naam `shunchi` (Analytics off).
2. **Build -> Authentication -> Get started**.
   - **Sign-in method -> Email/Password -> Enable**.
   - **Google -> Enable** (support email = apnar Gmail).
3. **Build -> Firestore Database -> Create database** -> Production mode -> location `asia-south1` (ba nikoter).
4. **Firestore -> Rules** tab-e `firebase/firestore.rules` file-er pura lekha paste kore **Publish**.
   (Admin email default `ruhulaaminn@gmail.com`. Onno hole rules-er prothom function-e ota bodle nin.)

## 2. Web config
1. **Project settings (gear) -> General -> Your apps -> Web (`</>`)** -> app register korun (Hosting lagbe na).
2. Je `firebaseConfig` dekhabe tar `apiKey`, `projectId`, `appId` (ar chaile `authDomain`) niye `site/data/firebase-config.json` e lekhun:
   ```json
   {"apiKey":"AIza...","authDomain":"shunchi-xxxx.firebaseapp.com","projectId":"shunchi-xxxx","appId":"1:123:web:abc"}
   ```
   Eta public thaka niraapod (secret na). Rules-i data-ke bachay.
3. **Authentication -> Settings -> Authorized domains** -> add: `shunchiai.com` ar `www.shunchiai.com`.
4. Commit/push korle website deploy hobe, login button dekhabe.

## 3. Admin
Admin panel -> **Users** tab -> **Sign in with Google** (rules-e deya admin Gmail diye). Tarpor user list, status (Active/Inactive/Blocked), data, comment moderation.

## 4. Desktop app Google login (optional)
Email/password app-e ager step-eii cholbe. App-e **Google** bhalo korte:
1. https://console.cloud.google.com -> same project -> **APIs & Services -> Credentials -> Create credentials -> OAuth client ID -> Desktop app**.
2. Client ID ar Client secret `site/data/firebase-config.json` e jog korun:
   `"googleClientId":"...apps.googleusercontent.com","googleClientSecret":"GOCSPX-..."`
   (Desktop app-er secret public hishabe dhora hoy, tobe ekhane thaka thik.)
3. Firebase -> Authentication -> Sign-in method -> Google -> **Web SDK configuration -> Safelist client IDs from external projects** e oi Client ID-ta add korun.

## Block ki kore kaj kore
`Blocked` hole user login korte pare, kintu rules-er karone comment/idea/data save korte pare na (website ar app duitei). Firebase Auth-er login account-i disable korte Firebase console lage; seta admin panel theke hoy na.
