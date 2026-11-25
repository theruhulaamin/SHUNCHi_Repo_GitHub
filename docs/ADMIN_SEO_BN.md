# অ্যাডমিন প্যানেল, ব্লগ ও SEO গাইড

## ১. অ্যাডমিন প্যানেল কী?
ঠিকানা: **https://shunchiai.com/gitup/**

এটি আপনার নিজের GitHub repository-র সাথে সংযুক্ত। এখান থেকে সফটওয়্যার ও ব্লগ লিখে Save চাপলে GitHub নিজেই ওয়েবসাইট রিবিল্ড করে (প্রায় ২ মিনিট)। আলাদা সার্ভার বা ডাটাবেস লাগে না, তাই ফ্রি।

### প্রথমবার: টোকেন বানান (একবারই)
1. GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate new token।
2. Name: `SHUNCHi admin`, Expiration: 90 days।
3. Repository access: **Only select repositories** → `shunchi_repo_github`।
4. Permissions → Repository: **Contents = Read and write**, **Actions = Read and write**, Metadata = Read।
5. Generate করে টোকেন কপি করুন, অ্যাডমিন পেজে পেস্ট করে **Connect** চাপুন।

টোকেন শুধু এই একটি repository-তে কাজ করে। কাউকে দেবেন না। "Remember on this device" শুধু নিজের পিসিতে টিক দিন।

### সফটওয়্যার পাবলিশ
Software ট্যাব → **Add software** → নাম, এক লাইনের বিবরণ (English/Bangla), ভার্সন, ডাউনলোড লিংক (https), লোগো দিন → **Save and publish**।
- ওয়েবসাইটে `/apps/<নাম>.html` নামে আলাদা পেজ তৈরি হবে (SEO-র জন্য)।
- More Apps ও হোমে তালিকায় আসবে, আর SHUNCHi অ্যাপের ভেতরেও দেখাবে।
- Status **Coming soon** দিলে পেজ গোপন থাকে ও গুগলে যায় না।

### ব্লগ লেখা
Blog ট্যাব → **New post** → Title, Summary, ভাষা, Article (Markdown) → **Save and publish**।
- Title ৬০ অক্ষরের মধ্যে, Summary ৭০–১৫৫ অক্ষর রাখুন (কাউন্টার সবুজ হলে ভালো)।
- Draft টিক দিলে পোস্ট পাবলিক হয় না।
- `[লেখা](/download/)` লিখে ভেতরের পেজে লিংক দিন।

### SHUNCHi-র নতুন ভার্সন রিলিজ
Release ট্যাব → ভার্সন লিখে বাটন চাপুন → GitHub-এ দুটি .exe attach করে Publish। বাকি সব অটো। বিস্তারিত: `docs/RELEASE_GUIDE_BN.md`।

## ২. SEO-র জন্য যা অটো আছে
- প্রতি পেজে আলাদা Title, Description, Canonical, Open Graph, Twitter Card।
- Google-এর জন্য Structured Data: WebSite, Organization, SoftwareApplication, FAQPage (হোমে), BlogPosting, BreadcrumbList, ItemList।
- `sitemap.xml` ও `feed.xml` (RSS) প্রতি বিল্ডে নতুন করে তৈরি হয়। `robots.txt` অ্যাডমিন পেজ আটকায়।
- টুল ও অ্যাপের তালিকা সরাসরি HTML-এ আছে, তাই JavaScript ছাড়াই গুগল পড়তে পারে।
- Coming soon / draft পেজ `noindex`, গুগলে যায় না (পাতলা কনটেন্টে র‍্যাংক নষ্ট হয় না)।
- দ্রুত লোড: ছোট CSS/JS, লেজি ইমেজ, মোবাইল-ফ্রেন্ডলি।

## ৩. আপনাকে যা করতে হবে (একবার, ১০ মিনিট)
1. **Google Search Console**: https://search.google.com/search-console → Add property → URL prefix `https://shunchiai.com` → ভেরিফাই (HTML tag দিলে আমাকে দিন, `<head>`-এ বসিয়ে দেব; অথবা DNS TXT রেকর্ড Hostnin-এ) → Sitemaps-এ `sitemap.xml` সাবমিট।
2. **Bing Webmaster Tools** (https://www.bing.com/webmasters): Search Console থেকে Import করা যায়।
3. নতুন পেজ পাবলিশ করলে Search Console → URL inspection → **Request indexing**।
4. Google Business/Facebook/Instagram পেজে ওয়েবসাইটের লিংক দিন। ব্যাকলিংক র‍্যাংক বাড়ায়।

## ৪. র‍্যাংক করতে সময় ও কনটেন্ট
কোনো টেকনিক্যাল ব্যবস্থা র‍্যাংকের নিশ্চয়তা দেয় না। নতুন সাইটে সাধারণত কয়েক সপ্তাহ থেকে কয়েক মাস লাগে। সবচেয়ে কাজের জিনিস:
- নিয়মিত ব্লগ (সপ্তাহে ১–২টি): "বাংলা ভয়েস টাইপিং", "Bangla voice typing Windows", "ফ্রি Gemini API key" এই ধরনের প্রশ্নের উত্তর।
- প্রতিটি টুল চালু করার সময় আলাদা পেজ ও তার ব্যবহার-গাইড।
- ইউটিউব ভিডিও, ফেসবুক গ্রুপে শেয়ার, অন্য সাইট থেকে লিংক।

## Notun Admin panel (v2): ki ki ache

- **Dashboard**: total download (release wise), live version, website build status, GitHub stars, repo views, recent builds.
- **Ideas**: website-er idea form-er sob data. Ekbar FormSubmit API key boshale (Ideas tab-e dhap deya ache) shob idea ekhane dekha jay. Search, filter, CSV download, "Reply by email".
- **Software**: add/edit/delete, logo upload, protiti software-er download count.
- **Blog**: WYSIWYG editor (Word-er moto). Image paste/drag-drop/upload (auto chhoto hoy), alt text, cover image, SEO checklist, Draft/Publish, Markdown mode.
- **Release**: 4 dhap-er wizard (Bangla + English). Version, note, duita installer file dile admin nijei GitHub-e upload kore release publish kore, tarpor website live howa porjonto dekhay. Browser upload block korle "Do it on GitHub instead" button ache.
- Token-e **Administration: Read** permission dile repo view-er number-o dekha jay (optional).
