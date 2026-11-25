# শুনছি ওয়েবসাইট: ফ্রিতে পাবলিশ ও shunchiai.com কানেক্ট

## ১. GitHub-এ আপলোড
1. github.com-এ নতুন **Public** রিপোজিটরি খুলুন (নাম: `shunchi`)। ফ্রি Pages সাধারণত পাবলিক রিপোতেই চলে।
2. এই ফোল্ডারে টার্মিনাল খুলে:
```
git init -b main
git add .
git commit -m "SHUNCHi website"
git remote add origin https://github.com/<আপনার-ইউজারনেম>/shunchi.git
git push -u origin main
```

## ২. Pages চালু
Repo → **Settings → Pages → Source = GitHub Actions**। এরপর Actions ট্যাবে "Deploy website" সবুজ হলে সাইট `https://<ইউজারনেম>.github.io/shunchi/` এ উঠবে।

## ৩. কাস্টম ডোমেইন (আগে GitHub-এ, তারপর DNS)
1. Settings → Pages → **Custom domain** = `shunchiai.com` → Save। (`site/CNAME` ফাইল আগেই দেওয়া আছে।)
2. ডোমেইন প্রদানকারীর DNS-এ যোগ করুন:
   - `A` @ → 185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153
   - (ঐচ্ছিক IPv6) `AAAA` @ → 2606:50c0:8000::153 … 8001::153, 8002::153, 8003::153
   - `CNAME` www → `<ইউজারনেম>.github.io`
3. DNS ছড়াতে ২৪ ঘণ্টা পর্যন্ত লাগতে পারে। এরপর **Enforce HTTPS** টিক দিন।
- Cloudflare DNS ব্যবহার করলে প্রথমে রেকর্ডগুলো **DNS only** (ধূসর মেঘ) রাখুন।
- বিকল্প ফ্রি হোস্ট: Cloudflare Pages বা Netlify; `site` ফোল্ডারই পাবলিশ ডিরেক্টরি।

## ৪. নতুন ভার্সন রিলিজ (অ্যাডমিন প্যানেলের বদলে)
1. `Build_Installer.bat` + Inno Setup দিয়ে `SHUNCHi_Setup_x.y.z.exe` বানান।
2. GitHub → **Releases → Draft a new release** → Tag `v4.5.0` → ইনস্টলার ফাইল অ্যাটাচ করুন → রিলিজ নোট লিখুন → **Publish**।
3. স্বয়ংক্রিয়ভাবে `update.json` আপডেট হয়ে সাইট ডিপ্লয় হয়; ব্যবহারকারীরা অ্যাপে আপডেটের খবর ও ডাউনলোড বাটন পান (অ্যাপ ~৬ ঘণ্টা পরপর চেক করে)।
- অন্য অ্যাপের ট্যাগ: `my-app-v1.0.0`।

## ৫. নতুন টুল পেজ
`site/apps/_template.html` কপি করে `site/apps/<id>.html` নাম দিন, টুল বানান, তারপর `assets/catalog.js`-এ ওই টুলের `s: "soon"` বদলে `s: "live"` করুন।

## মনে রাখবেন
- ইনস্টলার সাইন করা নয়, তাই SmartScreen-এ "More info → Run anyway" লাগে।
- `admin/` PHP প্যানেল শুধু পরে পেইড PHP হোস্টিং নিলে লাগবে; রিপোতে রাখা হয়নি।
